# RELATÓRIO — BRECHORISEE v4.9.0 MÓDULOS 360

## Objetivo
Reduzir erros operacionais e iniciar uma modularização real do sistema, criando fluxos independentes para manutenção futura.

## Correções e melhorias adicionadas

### 1. Módulos 360
Nova central em `/modulos` com acesso rápido para:
- Calculadora
- Montante da cliente
- Inventário por câmera/código
- Consultor de estilo
- Checklist técnico

### 2. Calculadora BRECHORISEE
Nova rota `/calculadora`.

Calcula:
- preço sugerido
- preço após desconto
- lucro bruto
- margem
- divisão consignado: valor da cliente/fornecedora e valor do brechó
- ponto mínimo de equilíbrio

API:
- `POST /api/calculadora/preco`

### 3. Montante da cliente
Nova rota `/consignado`.

Fluxo implementado:
1. Seleciona cliente.
2. Adiciona montante/crédito.
3. Escaneia ou digita o código da peça.
4. O sistema debita o valor da peça.
5. Marca a peça como vendida.
6. Gera venda.
7. Registra movimento.
8. Retorna saldo final da cliente.

APIs:
- `GET /api/consignado/clientes`
- `GET /api/consignado/saldo/{customer_id}`
- `POST /api/consignado/credito`
- `POST /api/consignado/escanear`

### 4. Inventário por câmera/código
Nova rota `/inventario-camera`.

Fluxo:
1. Criar sessão de inventário.
2. Ler/digitar código da peça.
3. Conferir se existe no estoque.
4. Registrar encontrado/não encontrado.
5. Opcionalmente ajustar status: disponível, reservado, vendido, perdido ou manutenção.

APIs:
- `POST /api/inventario/sessao`
- `POST /api/inventario/escanear`
- `GET /api/inventario/sessao/{session_id}`

### 5. Consultor de estilo / Instagram
Nova rota `/consultor-estilo`.

Busca cliente por:
- nome
- telefone
- @instagram cadastrado

Gera sugestões usando:
- histórico de compras
- preferências cadastradas
- tamanho/cor/estilo informados
- membro da família informado

API:
- `GET /api/consultor-estilo/sugerir`

Observação: o sistema não faz scraping nem acessa Instagram privado. Ele usa o @ salvo no cadastro e dados internos da loja.

### 6. Checklist técnico
Nova rota `/sistema/checklist`.

Verifica:
- banco de dados
- APK Cliente publicado
- link público
- tabelas dos módulos 360

API:
- `GET /api/sistema/checklist`

## Modularização
Foi criada a pasta:

`BRECHORISEE_SERVIDOR/app/brechorisee_app/modules/`

com documentação para separar progressivamente o monólito `app.py` em routers FastAPI.

## Limitações honestas
- A identificação visual por câmera continua baseada no reconhecimento já existente por imagem/foto e leitura de código/QR. Para reconhecimento visual avançado de roupas por IA treinada seria necessário dataset e modelo próprio.
- O consultor Instagram não acessa perfil privado nem raspa dados da rede social. Ele usa os dados cadastrados no sistema.
- A modularização total do `app.py` deve ser feita em fases para não quebrar rotas existentes.

## Versão
`4.9.0-modulos-360`
