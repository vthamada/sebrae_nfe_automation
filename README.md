# Gestão local de NF-e para o Emissor Sebrae

Aplicação local em **Python + SQLite + Playwright** para controlar produtos,
clientes, preços, estoque e a fila de notas que precisam ser emitidas.

## Limite operacional importante

O núcleo local está funcional. A aplicação **não envia nem transmite NF-e no portal
Sebrae**. As notas em `READY_TO_ISSUE` devem ser emitidas manualmente e conferidas
no portal; somente depois a emissão é registrada localmente com número e chave de
acesso.

Essa separação é deliberada. Existe agora um **assistente supervisionado de
rascunhos no Chrome normal**, separado dos métodos antigos do Playwright, que
permanecem bloqueados. Ele prepara/salva somente rascunhos; a instalação e a
homologação no portal real ainda estão pendentes. Não há botão de emissão.

Consulte [RPA_GUIDE.md](RPA_GUIDE.md) para preparar o JSON, instalar manualmente a
extensão local, conferir o pedido e tratar falhas sem duplicar notas.

## Instalação no Windows

Execute:

```bat
install.bat
```

O instalador cria a `.venv`, instala as versões travadas em `requirements.lock`,
instala o Chromium do Playwright e inicializa o banco.

Por padrão, banco, perfil do navegador, logs e screenshots ficam fora do
repositório, em `%LOCALAPPDATA%\SebraeNFeAutomation`.

## Fluxo diário

Todos os comandos abaixo podem usar `run_manager.bat`.

### 1. Cadastrar um produto novo

```bat
run_manager.bat produto-adicionar --codigo PROD-001 --descricao "TENIS MODELO X" --unidade UN --custo "120,00" --preco "199,90" --estoque 10 --estoque-minimo 2 --ncm 64041100
```

- código e código de barras podem ser omitidos; o sistema gera valores únicos;
- preço e custo aceitam vírgula brasileira e são guardados em centavos inteiros;
- quantidade aceita até três casas decimais;
- o estoque informado no cadastro gera um movimento `INITIAL` auditável;
- NCM, CEST e CFOP têm validação de formato, mas a classificação tributária deve
  ser confirmada por responsável fiscal/contábil.

Para alterar o preço:

```bat
run_manager.bat produto-atualizar --codigo PROD-001 --preco "209,90" --motivo "NOVA TABELA AGOSTO"
```

O histórico registra preço anterior, novo preço, motivo e data. Notas que já
existem mantêm o preço congelado no momento em que foram criadas.

Para uma entrada ou correção de estoque:

```bat
run_manager.bat estoque-ajustar --codigo PROD-001 --quantidade 5 --motivo "ENTRADA COMPRA 123"
run_manager.bat estoque-ajustar --codigo PROD-001 --quantidade -1 --motivo "AVARIA"
```

O sistema não permite saldo negativo nem ajuste que reduza o saldo abaixo da
quantidade já reservada.

### 2. Cadastrar um cliente novo

Pessoa física:

```bat
run_manager.bat cliente-adicionar --documento 52998224725 --nome "CLIENTE TESTE" --email cliente@example.com --uf MG
```

Pessoa jurídica:

```bat
run_manager.bat cliente-adicionar --documento 11222333000181 --nome "EMPRESA TESTE LTDA" --fantasia "EMPRESA TESTE" --inscricao-estadual ISENTO --uf MG
```

CPF e CNPJ são normalizados e validados pelos dígitos verificadores. O documento é
único; uma tentativa de duplicidade é recusada. Endereço, inscrição estadual e
demais campos podem ser completados com as opções exibidas por:

```bat
run_manager.bat cliente-adicionar --help
```

### 3. Criar uma nota a partir de um pedido

```bat
run_manager.bat nota-criar --referencia PEDIDO-123 --cliente 52998224725 --item "PROD-001;2" --item "PROD-002;1;79,90;5,00" --observacoes "ENTREGA COMBINADA"
```

Formato do item:

```text
CODIGO;QUANTIDADE[;PRECO_UNITARIO[;DESCONTO_TOTAL_DO_ITEM]]
```

Ao criar a nota:

1. cliente e produtos ativos são conferidos;
2. preço atual é copiado para cada item, salvo quando há preço explícito;
3. totais são calculados em centavos, sem `float`;
4. estoque disponível é validado;
5. quantidade é reservada;
6. a nota fica em `DRAFT` para conferência.

A mesma referência e os mesmos itens podem ser reenviados sem duplicar a nota ou a
reserva. Se a referência for reutilizada com conteúdo diferente, a operação falha.

### 4. Revisar e colocar na fila de emissão

Depois de conferir cliente, itens, preços, descontos, dados fiscais e observações:

```bat
run_manager.bat nota-pronta --id 1
```

Para ver somente o que precisa ser emitido:

```bat
run_manager.bat notas-a-emitir
```

Somente notas `READY_TO_ISSUE` aparecem nessa fila.

### 5. Registrar uma emissão confirmada

Após emitir manualmente no portal Sebrae e conferir o resultado:

```bat
run_manager.bat nota-emitida --id 1 --numero 123 --chave 11111111111111111111111111111111111111111112
```

Essa operação valida os 44 dígitos e o dígito verificador da chave, muda a nota para `EMITTED`, converte a
reserva em saída e reduz o estoque físico. Ela **não transmite a nota no portal**.

Se o pedido for cancelado antes da emissão:

```bat
run_manager.bat nota-cancelar --id 1 --motivo "PEDIDO CANCELADO PELO CLIENTE"
```

A reserva é liberada. Uma nota já marcada como emitida não pode ser cancelada por
esse comando, porque cancelamento fiscal e eventual retorno ao estoque exigem um
fluxo próprio e confirmação no portal.

## Estados da nota e efeito no estoque

| Estado | Significado | Estoque físico | Estoque reservado |
| --- | --- | ---: | ---: |
| `DRAFT` | Em conferência | não muda | aumenta |
| `READY_TO_ISSUE` | Deve ser emitida | não muda | permanece reservado |
| `EMITTED` | Emissão confirmada | diminui | diminui |
| `CANCELLED` | Cancelada antes da emissão | não muda | é liberado |

O estoque disponível mostrado ao usuário é:

```text
estoque físico - estoque reservado
```

Produtos no mínimo podem ser listados com:

```bat
run_manager.bat estoque-baixo
```

O histórico completo de preço e estoque de um produto pode ser consultado com:

```bat
run_manager.bat produto-historico --codigo PROD-001
```

## Consultas úteis

```bat
run_manager.bat listar-produtos
run_manager.bat listar-clientes
run_manager.bat listar-notas
run_manager.bat listar-notas --status DRAFT
run_manager.bat listar-notas --status EMITTED
```

## Conciliação com o portal Sebrae

Depois de capturar um snapshot pela sessão autenticada do Chrome, execute:

```bat
run_reconciliation.bat --snapshot logs\sebrae_snapshot_20260825.json
```

O comando compara, sem alterar dados:

- produtos por código de barras quando disponível e depois por descrição
  normalizada;
- preço de venda, categoria, subcategoria e situação ativa;
- clientes por e-mail e depois por nome;
- saldo de estoque somente para as linhas efetivamente capturadas.

O relatório detalhado é gravado em `logs/` e o terminal mostra apenas contagens e
bloqueios. Use `--details` somente em ambiente privado, porque o resultado pode
conter nomes e contatos de clientes.

Não existe opção de aplicação automática. Duplicidades, banco vazio, ausência de
documentos dos clientes ou snapshot parcial de estoque mantêm
`safe_to_apply=false`.

## Inspector do portal Sebrae

O acesso ao host de produção é bloqueado por padrão. Para uma inspeção
supervisionada, copie `.env.example` para `.env`, revise a URL e defina
temporariamente:

```dotenv
ALLOW_PRODUCTION=true
```

O lançador abre por padrão a sessão normal e já autenticada do Google Chrome. A
captura da interface é feita pela conexão autorizada do Chrome no Codex. O
processo local não lê nem copia cookies dessa sessão.

Depois de navegar até a tela desejada, solicite a captura na conversa do Codex.
O terminal encerra após abrir a aba; pressionar ENTER nele não dispara a captura.

Se o Chrome não for localizado automaticamente, configure:

```dotenv
BROWSER_EXECUTABLE=C:\Program Files\Google\Chrome\Application\chrome.exe
```

O perfil isolado permanece somente para investigação técnica:

```bat
run_inspector.bat --isolated-diagnostic
```

O Sebrae foi testado com dois perfis isolados e manteve a tela de carregamento por
incompatibilidade de sessão. Por isso esse modo não faz parte do fluxo diário. Ele
escuta apenas em `127.0.0.1` e usa uma porta aleatória.

Depois execute:

```bat
run_inspector.bat
```

O JSON contém atributos estruturais dos campos, mas não seus valores. Screenshot é
desativado por padrão porque pode conter dados pessoais ou fiscais. Se for realmente
necessário:

```bat
run_inspector.bat --screenshot
```

Revise qualquer artefato antes de compartilhar e retorne `ALLOW_PRODUCTION=false`
ao terminar.

## Segurança e versionamento

- `.env`, bancos, perfil do navegador, cookies, logs, screenshots, exports,
  `.venv` e caches são ignorados pelo Git;
- senha, certificado e token nunca devem entrar no código;
- a automação valida HTTPS e uma lista explícita de hosts;
- o banco anterior à migração v2 foi preservado em
  `data/backups/sebrae.pre-v2-20260825.db`;
- não execute `git add -f` sobre arquivos ignorados que contenham dados reais.

## Verificação

```bat
.venv\Scripts\python.exe -m unittest discover -v
.venv\Scripts\python.exe -m pip check
```

Os testes cobrem valores monetários, CPF/CNPJ, migração do banco, cadastro,
histórico de preços, ajustes, reserva, falta de estoque, idempotência, emissão e
cancelamento antes da emissão.
