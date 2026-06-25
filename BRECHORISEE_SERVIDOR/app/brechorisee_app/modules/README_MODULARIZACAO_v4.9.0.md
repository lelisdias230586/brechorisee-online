# BRECHORISEE v4.9.0 — Modularização progressiva

O `app.py` legado ainda concentra muitas rotas. Nesta versão foi iniciada uma camada modular
com módulos operacionais independentes e banco próprio para cada fluxo.

## Módulos criados

- `calculadora`: preço, margem e comissão consignada.
- `montante_cliente`: carteira/montante da cliente, crédito, baixa por peça e saldo final.
- `inventario_camera`: conferência por código/QR e ajuste de status.
- `consultor_estilo`: sugestão por cliente, Instagram cadastrado, preferências e família.
- `checklist_sistema`: diagnóstico de APK, banco, link público e módulos.

## Próxima etapa recomendada

Separar fisicamente o `app.py` em routers FastAPI:

```
brechorisee_app/
  main.py
  core/db.py
  core/security.py
  modules/products/router.py
  modules/customers/router.py
  modules/consignado/router.py
  modules/inventory/router.py
  modules/style/router.py
  modules/android/router.py
```

A separação deve ser feita aos poucos para não quebrar o sistema que já está em produção.
