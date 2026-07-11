"""Runtime headless pour la Boring Parking Box."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from threading import Event, Thread

from dotenv import load_dotenv
from rich.console import Console

from boring.config import BoxConfig
from boring.capture import probe_camera
from boring.detect import Detector, StreamTracker, run_live_detection
from boring.events import EventLog
from boring.geofence import LilleParkingZones
from boring.glue import PaymentCooldown, PaymentLimits, make_payment_provider, process_trigger
from boring.network import NetworkMonitor, NetworkStatus, run_network_recovery
from boring.notify import notify
from boring.position import PositionProvider, make_position_provider
from boring.power import (
    BatteryStatus,
    LinuxPowerSupplyMonitor,
    LinuxThermalMonitor,
    ThermalStatus,
)
from boring.power_budget import build_power_budget
from boring.state import BoxStateStore
from boring.storage import DiskSpaceMonitor, DiskStatus
from boring.systemd import SystemdNotifier

console = Console()


@dataclass
class RuntimeState:
    low_battery_alert_sent: bool = False
    critical_battery_alert_sent: bool = False
    battery_saver_active: bool = False
    last_power_check: float = 0.0
    last_thermal_check: float = 0.0
    thermal_warning_alert_sent: bool = False
    thermal_critical_alert_sent: bool = False
    thermal_saver_active: bool = False
    last_network_check: float = 0.0
    last_disk_check: float = 0.0
    last_heartbeat: float = 0.0
    network_offline_alert_sent: bool = False
    network_online: bool | None = None
    last_network_recovery_attempt: float = -1_000_000_000.0
    disk_low_alert_sent: bool = False


def run_box_service(config: BoxConfig | None = None) -> None:
    """Lance le service boitier sans fenetre graphique."""
    load_dotenv()
    config = config or BoxConfig.from_env()
    state = RuntimeState()
    state_store = BoxStateStore(config.state_path)
    event_log = EventLog(
        config.event_log_path,
        max_bytes=config.event_log_max_bytes,
        backups=config.event_log_backups,
    )
    persisted = state_store.load()
    power = LinuxPowerSupplyMonitor()
    thermal = LinuxThermalMonitor()
    network = NetworkMonitor(config.network_probe_target)
    disk = DiskSpaceMonitor(config.event_log_path)
    systemd = SystemdNotifier.from_env()
    position_provider = make_position_provider(
        config.position_mode,
        config.lat,
        config.lon,
        config.gpsd_host,
        config.gpsd_port,
    )
    stop_event = Event()

    detector = Detector(
        model_path=config.model_path,
        target_labels=config.target_labels,
        confidence_threshold=config.confidence_threshold,
        device=config.detection_device,
    )
    tracker = StreamTracker(required_consecutive=config.consecutive_frames)
    cooldown = PaymentCooldown(
        cooldown_minutes=config.cooldown_minutes,
        last_payment=persisted.last_payment_at,
    )
    payment = make_payment_provider(dry_run=config.payment_dry_run)
    payment.login(os.getenv("PAYBYPHONE_USERNAME", ""), os.getenv("PAYBYPHONE_PASSWORD", ""))

    zones = _load_zones(config)
    initial_position = position_provider.current()
    if config.require_geofence and initial_position is None:
        notify(
            "Boring Box — position indisponible",
            "Paiement bloque: position absente.",
            sound=True,
        )

    notify(
        "Boring Box — service lance",
        f"camera={config.camera_device}, model={config.model_path}, provider={payment.name}",
        sound=False,
    )
    event_log.write(
        "service_started",
        camera_device=config.camera_device,
        model_path=config.model_path,
        provider=payment.name,
        payment_dry_run=config.payment_dry_run,
    )
    systemd.ready("Boring Box service started")

    monitor = Thread(
        target=_background_monitor,
        args=(stop_event, power, thermal, network, disk, systemd, state, config, event_log),
        daemon=True,
    )
    monitor.start()

    try:
        for detections in run_live_detection(
            detector=detector,
            fps=config.inference_fps,
            show_window=False,
            tracker=tracker,
            device_index=config.camera_device,
            fps_provider=lambda: _current_inference_fps(state, config),
        ):
            console.print(f"[red bold]TRIGGER[/red bold] — {len(detections)} detection(s)")
            _handle_trigger(
                payment=payment,
                cooldown=cooldown,
                state_store=state_store,
                event_log=event_log,
                state=state,
                config=config,
                position_provider=position_provider,
                zones=zones,
                detection_count=len(detections),
            )
    except Exception as exc:
        event_log.write("service_crashed", error=str(exc))
        notify("Boring Box — service plante", str(exc), sound=True)
        raise
    finally:
        systemd.stopping()
        stop_event.set()
        monitor.join(timeout=2)


def _background_monitor(
    stop_event: Event,
    power: LinuxPowerSupplyMonitor,
    thermal: LinuxThermalMonitor,
    network: NetworkMonitor,
    disk: DiskSpaceMonitor,
    systemd: SystemdNotifier,
    state: RuntimeState,
    config: BoxConfig,
    event_log: EventLog,
) -> None:
    while not stop_event.is_set():
        now = time.time()
        _check_power(now, power, state, config, event_log)
        _check_thermal(now, thermal, state, config, event_log)
        _check_network(now, network, state, config, event_log)
        _check_disk(now, disk, state, config, event_log)
        _heartbeat(now, state, config)
        systemd.watchdog("Boring Box monitor alive")
        stop_event.wait(
            max(
                1,
                min(
                    config.power_check_seconds,
                    config.thermal_check_seconds,
                    config.network_check_seconds,
                    config.disk_check_seconds,
                    config.heartbeat_seconds or 60,
                    systemd.watchdog_interval_seconds(),
                ),
            )
        )


def box_doctor(config: BoxConfig | None = None) -> int:
    """Verifications rapides avant installation sur le boitier."""
    load_dotenv()
    config = config or BoxConfig.from_env()
    errors = 0

    def check(ok: bool, label: str, detail: str = "") -> None:
        nonlocal errors
        marker = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
        console.print(f"{marker} {label}{f' — {detail}' if detail else ''}")
        if not ok:
            errors += 1

    check(config.vehicle_plate != "AA-000-AA", "plaque configuree", config.vehicle_plate)
    check(
        config.model_path == "yolov8n.pt" or os.path.exists(config.model_path),
        "modele present",
        config.model_path,
    )
    camera = probe_camera(config.camera_device)
    check(
        camera.ok,
        "camera accessible",
        f"device={config.camera_device}"
        + (f" {camera.width}x{camera.height}" if camera.ok else f" {camera.error}"),
    )
    check(config.zones_path.exists(), "zones de stationnement", str(config.zones_path))
    if config.state_path.is_absolute():
        check(
            config.state_path.parent.exists(),
            "dossier etat persistant",
            str(config.state_path.parent),
        )
    else:
        console.print(f"[yellow]WARN[/yellow] BOX_STATE_PATH relatif: {config.state_path}")
    if config.event_log_path.is_absolute():
        check(
            config.event_log_path.parent.exists(),
            "dossier journal evenements",
            str(config.event_log_path.parent),
        )
    else:
        console.print(f"[yellow]WARN[/yellow] BOX_EVENT_LOG_PATH relatif: {config.event_log_path}")
    position_provider = make_position_provider(
        config.position_mode,
        config.lat,
        config.lon,
        config.gpsd_host,
        config.gpsd_port,
    )
    position = position_provider.current()
    check(
        position is not None,
        "position boitier",
        config.position_mode if position is None else f"{position.lat:.5f},{position.lon:.5f}",
    )
    check(not config.payment_dry_run, "paiement reel active", "PAYMENT_DRY_RUN=false")
    check(
        config.max_session_amount_cents > 0,
        "plafond session",
        f"{config.max_session_amount_cents / 100:.2f} EUR",
    )
    check(
        config.max_daily_amount_cents >= config.max_session_amount_cents,
        "plafond journalier",
        f"{config.max_daily_amount_cents / 100:.2f} EUR",
    )
    budget = build_power_budget(
        capacity_wh=config.battery_capacity_wh,
        draw_watts=config.estimated_draw_watts,
        required_runtime_hours=config.required_runtime_hours,
        reserve_percent=config.power_reserve_percent,
        vehicle_charge_watts=config.vehicle_charge_watts,
        daily_drive_recharge_hours=config.daily_drive_recharge_hours,
        charge_efficiency=config.charge_efficiency,
    )
    if budget is None:
        console.print("[yellow]WARN[/yellow] budget energie non verifie")
    else:
        check(
            budget.parked_runtime_hours >= config.required_runtime_hours,
            "autonomie utile",
            f"{budget.parked_runtime_hours:.1f}h / requis {config.required_runtime_hours:.1f}h",
        )
        check(
            budget.has_vehicle_recharge,
            "recharge voiture",
            (
                f"{config.vehicle_charge_watts or 0:.1f}W input, "
                f"{budget.charge_surplus_watts:.1f}W surplus"
            ),
        )
    check(
        bool(config.notify_webhook_url),
        "webhook notification",
        "BORING_NOTIFY_WEBHOOK_URL configure" if config.notify_webhook_url else "missing",
    )
    network_status = NetworkMonitor(config.network_probe_target).check()
    check(network_status.online, "reseau", config.network_probe_target)
    check(
        bool(config.network_recovery_command),
        "recuperation reseau",
        config.network_recovery_command or "NETWORK_RECOVERY_COMMAND missing",
    )
    disk_status = DiskSpaceMonitor(config.event_log_path).check()
    if disk_status is None:
        console.print("[yellow]WARN[/yellow] espace disque non verifie")
    else:
        check(
            disk_status.free_mb >= config.disk_min_free_mb,
            "espace disque libre",
            f"{disk_status.free_mb}MB / requis {config.disk_min_free_mb}MB",
        )
    status = LinuxPowerSupplyMonitor().read()
    if status is None:
        console.print("[yellow]WARN[/yellow] batterie non detectee via /sys/class/power_supply")
    else:
        console.print(
            f"[green]OK[/green] batterie detectee — {status.percent}% source={status.source}"
        )
    thermal = LinuxThermalMonitor().read()
    if thermal is None:
        console.print("[yellow]WARN[/yellow] temperature CPU non detectee via /sys/class/thermal")
    else:
        check(
            thermal.temp_c < config.thermal_critical_c,
            "temperature CPU",
            f"{thermal.temp_c:.1f}C / critique {config.thermal_critical_c:.1f}C",
        )
    return 1 if errors else 0


def _load_zones(config: BoxConfig) -> LilleParkingZones | None:
    try:
        return LilleParkingZones(config.zones_path)
    except FileNotFoundError:
        return None


def _resolve_paid_zone(
    config: BoxConfig,
    zones: LilleParkingZones | None,
    lat: float,
    lon: float,
) -> bool:
    if zones is None:
        return not config.require_geofence
    return zones.is_in_paid_zone(lat, lon)


def _check_power(
    now: float,
    power: LinuxPowerSupplyMonitor,
    state: RuntimeState,
    config: BoxConfig,
    event_log: EventLog | None = None,
) -> BatteryStatus | None:
    if now - state.last_power_check < config.power_check_seconds:
        return None
    state.last_power_check = now
    status = power.read()
    if status is None or status.percent is None:
        return status
    saver_active = status.percent <= config.battery_low_percent and not status.charging
    if saver_active != state.battery_saver_active:
        state.battery_saver_active = saver_active
        if event_log is not None:
            event_log.write(
                "power_saver_changed",
                source="battery",
                active=saver_active,
                percent=status.percent,
            )
    if status.percent <= config.battery_critical_percent and not state.critical_battery_alert_sent:
        if event_log is not None:
            event_log.write("battery_critical", percent=status.percent, source=status.source)
        notify("Boring Box — batterie critique", f"{status.percent}% restants", sound=True)
        state.critical_battery_alert_sent = True
        state.low_battery_alert_sent = True
    elif status.percent <= config.battery_low_percent and not state.low_battery_alert_sent:
        if event_log is not None:
            event_log.write("battery_low", percent=status.percent, source=status.source)
        notify("Boring Box — batterie faible", f"{status.percent}% restants", sound=True)
        state.low_battery_alert_sent = True
    if status.charging:
        state.low_battery_alert_sent = False
        state.critical_battery_alert_sent = False
        if state.battery_saver_active:
            state.battery_saver_active = False
            if event_log is not None:
                event_log.write(
                    "power_saver_changed",
                    source="battery",
                    active=False,
                    percent=status.percent,
                )
    return status


def _check_thermal(
    now: float,
    thermal: LinuxThermalMonitor,
    state: RuntimeState,
    config: BoxConfig,
    event_log: EventLog | None = None,
) -> ThermalStatus | None:
    if now - state.last_thermal_check < config.thermal_check_seconds:
        return None
    state.last_thermal_check = now
    status = thermal.read()
    if status is None:
        return None
    thermal_saver_active = status.temp_c >= config.thermal_warning_c
    if thermal_saver_active != state.thermal_saver_active:
        state.thermal_saver_active = thermal_saver_active
        if event_log is not None:
            event_log.write(
                "power_saver_changed",
                source="thermal",
                active=thermal_saver_active,
                temp_c=status.temp_c,
            )
    detail = f"{status.temp_c:.1f}C" + (f" ({status.label})" if status.label else "")
    if status.temp_c >= config.thermal_critical_c and not state.thermal_critical_alert_sent:
        if event_log is not None:
            event_log.write(
                "thermal_critical",
                temp_c=status.temp_c,
                source=status.source,
                label=status.label,
            )
        notify("Boring Box — temperature critique", detail, sound=True)
        state.thermal_critical_alert_sent = True
        state.thermal_warning_alert_sent = True
    elif status.temp_c >= config.thermal_warning_c and not state.thermal_warning_alert_sent:
        if event_log is not None:
            event_log.write(
                "thermal_warning",
                temp_c=status.temp_c,
                source=status.source,
                label=status.label,
            )
        notify("Boring Box — temperature elevee", detail, sound=True)
        state.thermal_warning_alert_sent = True
    elif status.temp_c < config.thermal_warning_c:
        if state.thermal_warning_alert_sent or state.thermal_critical_alert_sent:
            if event_log is not None:
                event_log.write(
                    "thermal_recovered",
                    temp_c=status.temp_c,
                    source=status.source,
                    label=status.label,
                )
            notify("Boring Box — temperature revenue", detail, sound=False)
        state.thermal_warning_alert_sent = False
        state.thermal_critical_alert_sent = False
    return status


def _current_inference_fps(state: RuntimeState, config: BoxConfig) -> float:
    if state.battery_saver_active or state.thermal_saver_active:
        return max(0.1, config.low_power_inference_fps)
    return max(0.1, config.inference_fps)


def _check_network(
    now: float,
    network: NetworkMonitor,
    state: RuntimeState,
    config: BoxConfig,
    event_log: EventLog | None = None,
) -> NetworkStatus | None:
    if now - state.last_network_check < config.network_check_seconds:
        return None
    state.last_network_check = now
    status = network.check()
    state.network_online = status.online
    if not status.online and not state.network_offline_alert_sent:
        if event_log is not None:
            event_log.write("network_offline", target=status.target, error=status.error)
        notify(
            "Boring Box — reseau indisponible",
            f"Autopaiement risque d'echouer ({status.target})",
            sound=True,
        )
        state.network_offline_alert_sent = True
    if not status.online:
        _attempt_network_recovery(now, state, config, event_log)
    elif status.online and state.network_offline_alert_sent:
        if event_log is not None:
            event_log.write("network_recovered", target=status.target)
        notify("Boring Box — reseau revenu", f"Probe OK: {status.target}", sound=False)
        state.network_offline_alert_sent = False
    return status


def _attempt_network_recovery(
    now: float,
    state: RuntimeState,
    config: BoxConfig,
    event_log: EventLog | None = None,
) -> None:
    command = config.network_recovery_command
    if not command:
        return
    if now - state.last_network_recovery_attempt < config.network_recovery_cooldown_seconds:
        return
    state.last_network_recovery_attempt = now
    result = run_network_recovery(
        command,
        timeout_seconds=config.network_recovery_timeout_seconds,
    )
    if event_log is not None:
        event_log.write(
            "network_recovery_attempted",
            command=result.command,
            ok=result.ok,
            returncode=result.returncode,
            error=result.error,
            stderr=result.stderr[-500:] if result.stderr else "",
        )
    if not result.ok:
        notify(
            "Boring Box — recovery reseau echoue",
            result.error or result.stderr or f"exit={result.returncode}",
            sound=True,
        )


def _check_disk(
    now: float,
    disk: DiskSpaceMonitor,
    state: RuntimeState,
    config: BoxConfig,
    event_log: EventLog | None = None,
) -> DiskStatus | None:
    if now - state.last_disk_check < config.disk_check_seconds:
        return None
    state.last_disk_check = now
    status = disk.check()
    if status is None:
        return None
    if status.free_mb < config.disk_min_free_mb and not state.disk_low_alert_sent:
        if event_log is not None:
            event_log.write(
                "disk_low",
                path=status.path,
                free_mb=status.free_mb,
                min_free_mb=config.disk_min_free_mb,
            )
        notify(
            "Boring Box — stockage faible",
            f"{status.free_mb}MB libres sur {status.path}",
            sound=True,
        )
        state.disk_low_alert_sent = True
    elif status.free_mb >= config.disk_min_free_mb and state.disk_low_alert_sent:
        if event_log is not None:
            event_log.write("disk_recovered", path=status.path, free_mb=status.free_mb)
        notify("Boring Box — stockage OK", f"{status.free_mb}MB libres", sound=False)
        state.disk_low_alert_sent = False
    return status


def _handle_trigger(
    *,
    payment,
    cooldown: PaymentCooldown,
    state_store: BoxStateStore,
    event_log: EventLog,
    state: RuntimeState,
    config: BoxConfig,
    position_provider: PositionProvider,
    zones: LilleParkingZones | None,
    detection_count: int,
):
    if state.network_online is False:
        event_log.write(
            "payment_skipped_offline",
            plate=config.vehicle_plate,
            detection_count=detection_count,
        )
        notify(
            "Boring Box — paiement bloque",
            "Reseau indisponible: impossible de payer automatiquement.",
            sound=True,
        )
        return None

    position = position_provider.current()
    if position is None:
        event_log.write("payment_skipped_no_position", plate=config.vehicle_plate)
        notify(
            "Boring Box — paiement bloque",
            "Position indisponible: impossible de verifier la zone payante.",
            sound=True,
        )
        return None

    in_paid_zone = _resolve_paid_zone(config, zones, position.lat, position.lon)
    if not in_paid_zone:
        event_log.write(
            "payment_skipped_outside_paid_zone",
            plate=config.vehicle_plate,
            lat=position.lat,
            lon=position.lon,
            source=position.source,
        )

    def on_success(session) -> None:
        state_store.record_session(session)
        event_log.write(
            "payment_success",
            provider=session.provider,
            session_id=session.session_id,
            plate=session.vehicle_plate,
            amount_cents=session.amount_cents,
        )

    return process_trigger(
        payment=payment,
        cooldown=cooldown,
        in_paid_zone=in_paid_zone,
        plate=config.vehicle_plate,
        duration_minutes=config.default_duration_minutes,
        lat=position.lat,
        lon=position.lon,
        on_success=on_success,
        payment_limits=PaymentLimits(
            max_session_amount_cents=config.max_session_amount_cents,
            max_daily_amount_cents=config.max_daily_amount_cents,
            already_paid_today_cents=state_store.paid_today_cents(),
        ),
    )


def _heartbeat(now: float, state: RuntimeState, config: BoxConfig) -> None:
    if config.heartbeat_seconds <= 0:
        return
    if now - state.last_heartbeat < config.heartbeat_seconds:
        return
    state.last_heartbeat = now
    notify("Boring Box — alive", "Service actif, detection en cours.", sound=False)
