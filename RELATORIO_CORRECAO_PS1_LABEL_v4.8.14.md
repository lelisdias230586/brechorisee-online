# RELATÓRIO - Correção do BAT/PowerShell v4.8.14

## Problema corrigido

O PowerShell parava antes de executar o processo com erro de parser:

```text
Referência de variável inválida. ':' não era seguido de um caractere de nome de variável válido.
```

A linha problemática era:

```powershell
Log "Validando APK $label:"
```

No PowerShell, quando uma variável é seguida imediatamente por `:`, pode ser interpretada de forma ambígua. A correção foi delimitar a variável:

```powershell
Log "Validando APK ${label}:"
```

## Arquivos corrigidos

- `FAZER_TUDO_BRECHORISEE_WINDOWS.ps1`
- `FAZER_TUDO_BRECHORISEE_WINDOWS.bat`

## Resultado esperado

O script agora deve continuar para:

1. Gerar APK Cliente.
2. Validar APK Cliente.
3. Publicar APK Cliente no servidor.
4. Gerar APK Admin.
5. Validar APK Admin.
6. Criar `PACOTE_TERMUX_MINI`.
7. Criar `SISTEMA_BRECHORISEE_WINDOWS`.
8. Compactar os pacotes finais.

Versão: `4.8.14`
