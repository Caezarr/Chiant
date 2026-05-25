<!-- Merci de proposer une PR ! Quelques points avant submit. -->

## Quoi

<!-- Que fait cette PR en une phrase ? -->

## Pourquoi

<!-- Quel problème ça résout, ou quelle valeur ça apporte ? Lien vers une issue si applicable. -->

Closes #

## Comment tester

<!-- Étapes pour valider la PR : commandes, scénarios manuels, … -->

```bash
uv run pytest tests/
uv run boring …
```

## Checklist

- [ ] Tests pytest passent en local (`make test`)
- [ ] `make format` + `make lint` sans erreurs
- [ ] Pas de credentials / tokens commités (`.env` ignoré)
- [ ] CHANGELOG.md mis à jour si user-facing
- [ ] Documentation (README / docstrings) mise à jour si nécessaire
- [ ] Framing public reste "outil de paiement optimisé" (cf. README — avertissement juridique)
