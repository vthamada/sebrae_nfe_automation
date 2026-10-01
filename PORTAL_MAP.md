# Mapa do portal Emissor de NF-e Sebrae

Mapeamento somente leitura realizado em 25/08/2026 pela sessão autenticada do
Chrome normal. Valores de campos, linhas de clientes/notas, documentos, e-mails,
tokens e cookies não foram coletados.

O inventário estrutural completo está em
`logs/sebrae_ui_chrome_20260825_other_pages.json`.

## Cadastros

| Página | Rota | Estado do mapa |
| --- | --- | --- |
| Produtos | `#/item` | lista e formulário confirmados |
| Serviços | `#/service` | lista confirmada |
| Marcas | `#/brand` | colunas ID e Nome confirmadas |
| Categorias | `#/category` | coluna Nome confirmada |
| Unidades de Medida | `#/item_unit` | colunas ID, Sigla e Nome confirmadas |
| Clientes | `#/client` | lista e formulário confirmados |
| Fornecedores | rota filtrada de `#/supplier/search/` | lista confirmada |
| Transportadoras | rota filtrada de `#/supplier/search/` | lista confirmada |

### Produto novo

Campos e seções confirmados: ativo/inativo, descrição, tipo de item, unidade,
categoria, subcategoria, código de balança, marca, modelo, tags, código interno,
custo da última compra, venda no varejo, venda no atacado e quantidade mínima de
atacado.

Na aba Estoque foram confirmados tipo de estoque, movimentar estoque e os modos
Único e Grade. Na aba Fiscal foram confirmados Tipo, NCM, Origem, CEST e
Classificação. Os botões Salvar e Salvar e Voltar foram identificados, mas não
foram acionados.

### Cliente novo

Rota `#/client/new`. Campos confirmados: pessoa física/jurídica, bloqueado, nome,
apelido, CPF, RG, emissor, UF, sexo, aniversário, telefone, celular, e-mail, site,
observação, e-mail fiscal, ISS retido, consumidor final, produtor rural e endereço
(CEP, exterior, número, complemento e bairro). Também existem as abas Contatos,
Dados Bancários e Documentos. Nenhum cadastro foi salvo.

## Emissor fiscal

| Página | Rota/base | Estado do mapa |
| --- | --- | --- |
| Emissão NF-e | rota filtrada de `#/invoice/search/` | lista e início do formulário confirmados |
| Emissão NFC-e | rota filtrada de `#/invoice/search/` | lista confirmada |
| Emissão CT-e | rota filtrada de `#/invoice/search/` | lista confirmada |
| Desacordo de CT-e | `#/disagreement_cte` | página confirmada |
| Emissão NFS-e | rota filtrada de `#/invoice/search/` | lista confirmada |
| Consulta de Documentos | `#/invoice` | página confirmada |
| Notas Recebidas | `#/invoice_manifest` | página confirmada |

A lista de NF-e possui as colunas Número/Série, Origem, Destinatário, Emissão e
Valor. O formulário `#/invoice/new` possui Tipo de Nota, Entrada/Saída, datas e,
para Saída, destinatário/remetente, pessoa física/jurídica, CPF, RG, e-mail fiscal,
telefone e endereços de faturamento e entrega.

As etapas posteriores de itens, tributos e totais dependem da escolha de um
destinatário real. Elas não foram avançadas para evitar criar ou salvar um
rascunho fiscal inadvertidamente. Nenhuma nota foi transmitida.

## Ajustes

Foram confirmadas as páginas Configurações da Empresa, Fiscal Geral, Fiscal NF-e,
Matriz Fiscal, Matriz Fiscal IBS/CBS e Natureza de Operação. O mapa inclui somente
rótulos e controles, sem dados da empresa, certificado ou senha.

## Relatórios

- Produtos: categoria, subcategoria, item, código de barras, custo, varejo e atacado.
- Clientes: cliente, telefone e e-mail.
- Estoque: categoria, subcategoria, produto, código de barras, inicial, compras,
  vendas, entradas, saídas e saldo.

Os controles de exportação foram identificados, mas nenhuma exportação ou envio
foi executado.

## Limites operacionais

O perfil isolado do Playwright é rejeitado pelo portal durante a autenticação e
fica na tela de carregamento. O mapeamento válido depende da conexão autorizada do
Chrome normal no Codex. A automação de gravação permanece bloqueada até que cada
seletor necessário seja homologado e o fluxo seja testado sem transmissão.

## Atualização estrutural — 01/10/2026

O fluxo de rascunho foi observado na preparação supervisionada de uma nota real.
Nesta etapa de desenvolvimento, foram feitas apenas consultas e a abertura de
um formulário vazio; não foi criada outra nota. A nota antes preparada agora
aparece autorizada no portal. Não se deve reutilizá-la como teste de criação.

Alvos confirmados no DOM do formulário/detalhe:

| Seção | Alvos |
| --- | --- |
| Geral | `#formGeneralInfo`; `controller.currentInvoice.InvoiceModel`, `OperationTypeID`, `IssueDate`, `InputOutputDate` nos atributos `ng-model` |
| Cliente | `input[placeholder="Nome do cliente ou fornecedor"]`; documento e nome em `ng-model` |
| Operação | `controller.currentInvoice.TransactionNatureID`; `input[name="DefaultCfop"]` |
| Item | `form[name="newItemForm"]`; busca `DIGITE O NOME OU CÓDIGO DO ITEM`; `controller.newItem.Amount`, `ItemUnit`; `.bt-add-item` |
| Linhas | `.barcode`, `.name`, `.quantity b`, dois `td.price`, `.bt-discount` |
| Editor | `form[name="itemDiscountForm"]`; `controller.currentItem.Amount`, `Value`, `Discount`, `ItemUnit`, `Item.Ncm`; `controller.currentInvoiceItemCfop`; `label[for="submitItemDiscountForm"]` |
| Total | `.total-value.equal .value`; desconto/frete/seguro/despesas em `ng-model` |
| Transporte | `select[ng-model="controller.shippingTypeID"]` |
| Pix | `controller.newPaymentType`, `currentPaymentCondition`, `newPaymentTypeValue`; `.bt-select-payment`; `.payment-summary` |
| Rascunho | `button[title="Salvar"]`; confirmação `Nota salva com sucesso!`; rota `#/invoice/detail/<id>` |

A escolha de produto carrega dados assincronamente e redefine a quantidade para
1: aguarde unidade/valor carregados antes de ajustar quantidade. As condições de
Pix são próprias do cadastro da conta; a V1 interrompe se houver várias opções.

Presença e observação ficam disponíveis depois do primeiro salvamento. Os alvos
`#selConsumerPresenceCode` e `#txtAdditionalInformation` do novo assistente precisam
ser homologados no primeiro rascunho supervisionado; se estiverem ausentes, o ID
já salvo é preservado como `SAVED_REVIEW_PENDING`, sem criar outra nota.

`extension/` usa esses atributos **somente como seletores DOM**, sem acessar
objetos Angular, cookies ou endpoints internos. Os testes são locais/sintéticos;
não substituem homologação real. Consulte `RPA_GUIDE.md`.
