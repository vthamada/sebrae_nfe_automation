# Assistente supervisionado de rascunhos — V1

O Python valida um pedido e exporta um plano. Uma extensão local preenche a aba
do Chrome que **você já usa para acessar o Sebrae**, mediante clique explícito.
Não abre perfil isolado, não copia cookies e não exige depuração remota. O
`run_inspector.bat` continua sendo somente um lançador/inspector; pressionar Enter
nele não monta notas.

**Estado: implementação com testes automatizados locais; instalação e homologação
supervisionada no portal real ainda pendentes.** A extensão não foi instalada
automaticamente. Não foi criada nem emitida nota real para testar esta versão.

## Limites da primeira versão

- NF-e de saída, `Venda Dentro do Estado`, CFOP `5102`, explicitamente revisados.
- Pix com uma única condição de pagamento disponível no cadastro do portal.
- Sem ocorrência de transporte, frete zero e nenhum desconto/despesa adicional.
- Cliente e produtos **já cadastrados no portal**, com identificação exata.
- Quantidade com até três casas decimais; preços em centavos, positivos e abaixo
  de R$ 9.999.999,00 por unidade.
- Datas de emissão/entrega e presença precisam ser informadas; não são adivinhadas.
- Não cadastra clientes/produtos, não classifica tributos, não altera preço do
  catálogo e **não aciona Emitir ou Enviar**.

CFOP, NCM, origem, regime e tributação não são decididos pela automação. O CFOP
suportado não deve ser aplicado indiscriminadamente a novos produtos/operações.
Os dados fiscais precisam ser revisados pelo responsável fiscal/contábil.
O assistente interrompe em caso de divergência; não inventa campos ou classificação.

## 1. Preparar o pedido

Use `examples/pedido_rpa.json` como modelo. Ele contém **dados sintéticos** e não
deve ser enviado a uma empresa real. Crie o seu JSON em `exports/`, que é ignorada
pelo Git, preenchendo emitente, destinatário, códigos reais dos produtos, unidades
exatas do portal, preços e quantidades. Cada código só pode aparecer uma vez:
consolide sua quantidade. Informe `expected_total` para conferência independente.

```bat
run_rpa.bat rpa-preparar --pedido exports\pedido.json --saida exports\plano.json
```

Esse comando **não abre o navegador e não modifica o banco/estoque**. Gera um
plano `DRAFT_ONLY` com checksum e recusa sobrescrever um arquivo com outro pedido.
O checksum detecta alterações acidentais; não é assinatura digital nem proteção
contra alguém com acesso ao computador que deliberadamente gere outro arquivo.

`portal_code` é o código exibido na busca do Sebrae, não necessariamente um GTIN.
Descrição e unidade precisam corresponder ao cadastro. Um kit vendido como
`KI`/`CX` é um item na unidade do cadastro, não vários componentes inferidos.
Informe `presence` usando o código aplicável (`0`, `1`, `2`, `3`, `5` ou `9`);
consulte o responsável fiscal se houver dúvida, inclusive compras por WhatsApp.

## 2. Instalar manualmente no Chrome

Esta é uma extensão local, fora da loja. Antes de instalar, revise os arquivos e
as permissões. Ela pode ler/preencher a aba fiscal ativa depois do seu clique e
guarda um registro local de execução. Os planos ficam somente na memória do painel;
os arquivos exportados, entretanto, contêm dados comerciais/pessoais: proteja-os.

1. Abra `chrome://extensions` no **Chrome normal autenticado no Sebrae**.
2. Ative o modo do desenvolvedor e escolha **Carregar sem compactação**.
3. Selecione a pasta `D:\Users\DTI\Desktop\sebrae_nfe_automation\extension`.
4. Fixe “Sebrae — Assistente de rascunhos” no menu de extensões.

Permissões do manifesto: `activeTab`, `scripting`, `storage`. Não há acesso
permanente a todos os sites. Não solicita a API de cookies ou depurador e não lê
cookies, certificados ou senhas. Não há
serviço de nuvem/telemetria nem código remoto. A própria página do Sebrae mantém
suas comunicações normais. A extensão só aceita o host HTTPS do CNPJ do plano.

Não use o perfil isolado que apresentou carregamento infinito. Esta solução
aproveita a sessão normal; **não é uma correção da autenticação do perfil isolado**.

## 3. Montar, conferir e salvar

Antes, confira na lista do Sebrae se o pedido já possui nota/rascunho. O registro
da extensão **não conhece notas criadas manualmente ou por outros computadores**.
Também não substitui a conciliação com seu sistema de vendas.

1. No Sebrae, abra **Nova NF-e**, completamente vazia, sem escolher campos.
2. Clique na extensão **enquanto a aba Sebrae estiver ativa**. Ela abrirá um
   painel separado, associado àquela aba. Não precisa fechar o Sebrae.
3. Selecione `plano.json`, confira todos os dados e clique **Conferir aba**.
4. Marque a autorização de preenchimento/rascunho e clique **Montar rascunho**.
   Não mexa no formulário enquanto estiver executando.
5. Confira cliente, itens, quantidades, valores, CFOP, Pix e frete no portal.
6. Clique **Salvar e conferir**. O primeiro salvamento cria o rascunho e registra
   seu identificador; a revisão de presença/observação é salva **no mesmo ID**.
   A página é recarregada para conferir persistência. Não há transmissão fiscal.
7. Somente `SAVED_DRAFT` confirma esse fluxo. Exporte o resultado e revise a nota
   e seus dados fiscais no portal antes da emissão manual.

Se campos/formatos da conta diferirem do mapa, o assistente para. A primeira
execução real precisa ser acompanhada para homologar os seletores, sobretudo
presença/observação disponibilizados depois do salvamento. Os testes com página
simulada **não provam** compatibilidade com todas as contas ou versões do Sebrae.

## Falhas e prevenção de duplicidade

O diário é gravado em `chrome.storage.local` **antes** de preencher/salvar.
Contém checksum, situação, ID/URL da nota, total, número de itens e horário;
não contém sessão, cookies, plano completo ou endereços.

- `FILLED`: formulário montado; pode salvar pela mesma aba e pelo mesmo plano.
- `SAVE_STARTED`/`RUNNING`: execução incompleta; confira portal e registro.
- `UNCERTAIN`: pode ter ocorrido alteração/salvamento; **não repita**.
- `SAVED_REVIEW_PENDING`: ID de rascunho conhecido, revisão/persistência pendente.
  Abra esse rascunho e conclua a revisão manualmente; não crie outro.
- `SAVED_DRAFT`: rascunho salvo e conferido após recarregar, **não nota emitida**.

Use **Consultar registro** e **Exportar resultado** mesmo após uma falha. A mesma
referência é bloqueada se já iniciou ou se o conteúdo mudou. Há serialização para
impedir dois painéis de executar simultaneamente. Não apague o diário, desinstale
a extensão, troque o perfil ou invente outra referência para contornar uma falha:
isso remove/contorna a proteção local e pode duplicar notas. Não há desbloqueio
automático; reconcilie o que ficou na página/no portal antes de qualquer novo fluxo.

```bat
run_rpa.bat rpa-conferir-resultado --plano exports\plano.json --resultado exports\resultado.json
```

Essa conferência valida a estrutura do recibo local e sua ligação ao pedido;
**não consulta o Sebrae/SEFAZ**, não prova autorização fiscal e não baixa estoque.
Um recibo anterior também não informa se alguém emitiu/cancelou a nota depois.

## Se a nota já estiver no banco local

`nota-exportar-rpa` permite exportar `DRAFT`/`READY_TO_ISSUE`, com as quantidades e
preços congelados locais e um mapeamento explícito para produtos do portal.
O JSON de configuração usa os campos operacionais do pedido e uma seção:

```json
{
  "products": {
    "PROD-001": {"portal_code": "CODIGO-REAL", "description": "DESCRICAO EXATA", "unit": "UN"}
  }
}
```

```bat
run_rpa.bat nota-exportar-rpa --id 1 --config exports\config.json --saida exports\plano.json
```

O exemplo acima é só a seção de mapeamento: acrescente emitente, datas, operação,
CFOP, presença, pagamento e frete. Sem isso, a exportação é recusada. Notas já
emitidas não podem ser exportadas novamente. Descontos locais não são suportados
nesta primeira versão do assistente.

## Produtos, clientes, estoque e preços

Escolha uma fonte principal para os cadastros/estoque. Nesta V1, novos produtos e
clientes precisam ser cadastrados e revisados **no portal** antes de montar a
nota. O assistente não sincroniza cadastros nem saldos automaticamente.

- Preço do pedido: usado somente na linha da nota; não muda o preço do produto
  para vendas futuras. Quantidades/preços são conferidos item por item.
- Rascunho no portal: não implica baixa no banco local. Os efeitos do próprio
  Sebrae no seu estoque devem ser conferidos no portal.
- Pedido criado pelo núcleo local: continua reservando estoque como antes.
  Exportar ou salvar o rascunho não converte essa reserva em saída.
- Emissão: manual no portal, após revisão. Só registre `nota-emitida` localmente
  quando confirmar número e chave de autorização, para a nota local correta.
- Pedido que só existe no portal: não tem estoque/nota correspondente no SQLite.
  Não registre uma baixa local inventada ou uma segunda saída sem conciliação.

## Testes locais

```bat
.venv\Scripts\python.exe -m unittest discover -v
node --test tests/test_extension_protocol.cjs
```

Os novos testes cobrem protocolo Python/JavaScript, cálculos exatos, checksum,
host do emitente, dados obrigatórios, referência repetida, concorrência, falhas
incertas, preservação de ID, página já preenchida, NCM ausente e montagem/save/
recarregamento em HTML **sintético com todas as requisições interceptadas**.
O teste entre linguagens requer Node; o uso diário do assistente não requer Node.
O smoke MV3 também carrega a extensão em um perfil descartável de Chromium, sem
instalá-la no Chrome do usuário, e verifica a comunicação do painel com o diário.
