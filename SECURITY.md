# Security Policy

## Supported Versions

Boring (Chiant) est en pre-alpha. Toutes les versions 0.x sont considérées comme expérimentales et reçoivent les patchs de sécurité au coup par coup.

| Version | Supportée          |
|---------|--------------------|
| 0.x     | :white_check_mark: |

## Reporting a Vulnerability

Si tu identifies une vulnérabilité de sécurité, **ne la divulgue pas publiquement**. Contacte-nous d'abord :

- Email : `gabriel@meetwonka.com` (sujet préfixé `[SECURITY]`)
- Ou GitHub Security Advisory privé : https://github.com/Caezarr/Chiant/security/advisories/new

Inclus dans ton signalement :
- Description de la vuln
- Étapes pour reproduire
- Impact potentiel
- Version concernée (commit SHA)
- Patch suggéré si tu en as un

**Délai de réponse** : sous 7 jours ouvrés pour confirmer réception. Patch correctif sous 30 jours pour les vulnérabilités critiques.

## Périmètre

Cette politique couvre uniquement le code de ce repo. Les vulnérabilités dans les dépendances (ultralytics, opencv, httpx…) doivent être remontées aux mainteneurs respectifs — on les surveille via Dependabot.

## Hors périmètre

- Le code embarque des STUBs / mocks pour les APIs de paiement (PayByPhone, EasyPark, etc.). Les bugs ou comportements inattendus sur ces stubs sont des issues normales, pas des vulnérabilités.
- L'utilisation de Boring pour contourner intentionnellement le paiement légal du stationnement est hors périmètre — l'outil est conçu pour aider à payer, pas à éviter de payer.
