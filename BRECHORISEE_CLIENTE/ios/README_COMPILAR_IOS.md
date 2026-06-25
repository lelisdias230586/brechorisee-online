# BRECHORISEE iOS

Os projetos iOS foram preservados e separados em:

- `BRECHORISEE_CLIENTE\ios`
- `BRECHORISEE_ADMIN\ios`

Importante: o Windows não compila IPA nativo diretamente. Para gerar IPA é necessário:
- Mac com Xcode, ou
- serviço de build na nuvem como Codemagic/GitHub Actions com macOS.

No pacote Windows, o BAT central deixa os arquivos prontos e abre as instruções. 
A compilação Android e o servidor Windows são feitos localmente.
