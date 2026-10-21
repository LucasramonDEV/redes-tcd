# Diário de Aprendizado & Processo de Construção com IA

## Resumo técnico do aprendizado
- Modelagem de cabeçalho binário com `struct` (`!H H B B H H`: seq 16b, ack 16b, flags 8b, modo+janela 8b, max_text 16b, checksum 16b).
- Internet Checksum de 16 bits (soma em complemento de 1 com *carry around*).
- RC4 manual (KSA + PRGA) para o ponto extra de criptografia simétrica.
- FSM de cliente/servidor com `threading` (thread de recepção + thread de envio) e `threading.Lock()`.
- Handshake de 3 vias (SYN → SYN-ACK → ACK) com ISNs, estado `SYN_RCVD` e retransmissão por timer (ver caso 3 abaixo).

---

# Processo de construção e uso de IA

## 1. Estratégia de aprendizado com IA

Usamos a IA como **tutora e revisora**, não como gerador de código para colar. A regra do grupo era: *só entra no projeto o que algum de nós consegue explicar linha a linha ao monitor*. Na prática, o ciclo era:

1. **Perguntar o conceito antes do código.** Pedíamos primeiro a explicação (ex.: "como funciona o checksum de 16 bits?", "o que é KSA/PRGA?") e só depois a implementação, sempre proibindo bibliotecas prontas (`zlib`, `pycrypto`) nos pontos extras, para que a lógica fosse escrita à mão.
2. **Comparar com a especificação.** Cada trecho gerado era conferido contra o enunciado (payload ≤ 4 caracteres, janela, modos GBN/SR, handshake). Quando a IA propunha algo "mais fácil" (ex.: JSON no lugar de cabeçalho binário), recusávamos e pedíamos a versão aderente ao enunciado.
3. **Testar com falhas injetadas.** Usamos `--drop`, `--error` e logs do servidor para provar o comportamento, em vez de confiar na afirmação da IA de que "funciona".
4. **Pedir à IA que criticasse o próprio código** (e usar a nota/feedback do monitor como segunda revisão). Os dois erros mais importantes do projeto foram achados assim (casos abaixo).
5. **Registrar o que aprendemos** neste diário, em linguagem própria, para estudar para a arguição oral.

## 2. Casos concretos em que a IA errou

### Caso 1 (principal): handshake com apenas 2 vias — corrigido na Entrega 2

**O que a IA gerou.** Ao pedirmos o "handshake inicial", a IA entregou um protocolo SYN / SYN-ACK e descreveu isso como "handshake completo". No `server.py`, o estado ia para `ESTABLISHED` **imediatamente após o `sendto` do SYN-ACK**; no `client.py`, o cliente ia para `ESTABLISHED` ao receber o SYN-ACK e **nunca enviava o ACK final**.

**Por que está errado.** Um handshake de 3 vias existe justamente para que o servidor saiba que o cliente recebeu o SYN-ACK. No nosso código, se o SYN-ACK se perdesse na rede (UDP não garante entrega), o servidor ficaria "conectado" a um cliente que nunca soube disso — o servidor declarava sucesso sem ter recebido confirmação alguma.

**Como identificamos.** Não percebemos na primeira entrega: os testes locais (loopback, sem perdas) sempre funcionavam, então o erro ficou invisível. Foi o **monitor quem apontou** na correção da Entrega 1 (descontou 0,5 em 2,0 no item de handshake): *"o cliente recebe a resposta e encerra sem enviar o ACK final, e o servidor declara sucesso logo após o sendto"*. Releitura do código confirmou exatamente isso.

**Como corrigimos.** Mudamos o desenho do handshake, não só adicionamos um pacote:
- Servidor: `CLOSED → SYN_RCVD` ao receber o SYN (guarda o ISN do cliente, sorteia o seu), envia SYN-ACK (`seq=ISN_s`, `ack=ISN_c+1`) e **só vai para `ESTABLISHED` quando chega o ACK final** com `seq=ISN_c+1` e `ack=ISN_s+1` (valores conferidos; ACK inválido é ignorado).
- Cliente: ao receber um SYN-ACK válido (`ack == ISN_c+1`) envia o ACK final e então vai para `ESTABLISHED`.
- Confiabilidade do próprio handshake (UDP perde pacotes):
  - SYN perdido ou SYN-ACK perdido → o cliente **retransmite o SYN** (até 4 tentativas, 1 s cada).
  - ACK final perdido → o servidor tem um **timer em `SYN_RCVD`** e reenvia o SYN-ACK (até 5 vezes, depois abandona a conexão semiaberta); se o cliente receber um SYN-ACK duplicado, reenvia o ACK final.
  - Se chegar DATA enquanto o servidor ainda está em `SYN_RCVD` (ACK final perdido), o servidor descarta o dado e reenvia o SYN-ACK; o dado é recuperado pela retransmissão normal.
- Documentação (README, relatório técnico, manual de testes) atualizada para descrever o handshake de 3 vias.

**Lição.** Teste em loopback sem perdas não valida protocolo. Passamos a perguntar, para cada passo do protocolo, *"o que acontece se este pacote se perder?"* e *"quem sabe que o outro lado recebeu?"*.

### Caso 2: bug de `import random` local ao corrigir o handshake

Ao reescrever o início do `client.py` para sortear o ISN com `random.randint(...)`, a revisão do código (feita pela IA a nosso pedido, e confirmada por nós lendo o arquivo) mostrou que a função `main()` já continha um `import random` **dentro do loop de envio**. Em Python, um `import` dentro da função torna `random` uma variável local da função inteira; o uso de `random.randint` no começo de `main()` levantaria `UnboundLocalError` antes mesmo de enviar o SYN. Corrigimos movendo o `import random` para o topo do arquivo e removendo o import interno. Lição: a IA nos fez uma alteração correta localmente que quebrava o código por uma interação com código antigo — por isso releitura do arquivo inteiro, não só do trecho alterado.

### Caso 3: sockets bloqueantes e condições de corrida (fase de construção)

- **Problema:** a primeira versão sugerida pela IA fazia `sendto` e logo em seguida `recvfrom` na mesma thread. Se o ACK atrasava, o cliente travava e não conseguia tratar timeouts nem enviar o restante da janela de GBN/SR.
- **Correção:** separamos em duas threads (`receive_loop` só escuta; a thread principal roda a FSM de envio).
- **Efeito colateral:** apareceram erros intermitentes (`dictionary changed size during iteration`) porque as duas threads mexiam em `base`, `acks` e `timers` ao mesmo tempo. A IA explicou o conceito de condição de corrida e sugeriu `threading.Lock()`; aplicamos `with lock:` em todos os acessos ao estado compartilhado.

## 3. Prompt log

> **Como ler:** cada entrada traz o prompt (resumido/transcrito), o que a IA respondeu de útil, o que **estava errado ou foi recusado**, e o link/anexo da conversa.
>
> ⚠️ **PREENCHER ANTES DE ENTREGAR (grupo):** (1) substituir cada `[LINK/ANEXO]` pelo link compartilhado ou pelo arquivo exportado da conversa (colocar os arquivos em `relatorio/anexos_conversas_ia/`); (2) conferir se os prompts das linhas 4 e 5 correspondem ao que vocês realmente perguntaram e ajustar o texto se não; (3) apagar este aviso. Não entregar com placeholders.

| # | Fase | Prompt (resumo) | Resultado / o que aprendemos | Correção ou recusa | Link/anexo |
|---|------|-----------------|------------------------------|--------------------|------------|
| 1 | Arquitetura | "Estou construindo um TCD. A especificação diz que o texto deve ter até 4 caracteres, mas preciso mandar sequências e flags junto. A IA costuma gerar JSON, mas quero um pacote binário real. Como empacotar inteiros em bytes em Python?" | Introduziu `struct` com formato `!H H B B H H`; aprendemos a calcular o tamanho do cabeçalho em bytes. | Recusamos a proposta inicial em JSON. | [LINK/ANEXO] |
| 2 | Ponto extra 1 | "Como funciona matematicamente o checksum de 16 bits usado em redes reais? Não use zlib; quero escrever manipulando bits." | Soma de palavras de 16 bits, *carry around*, complemento de 1 (`~`). | — | [LINK/ANEXO] |
| 3 | Ponto extra 2 | "Qual cifra simétrica é simples o bastante para implementarmos sem biblioteca, só com XOR e vetores?" | RC4: KSA embaralha `S`; PRGA gera o keystream aplicado por XOR. | Recusamos usar biblioteca de criptografia. | [LINK/ANEXO] |
| 4 | Concorrência | "O cliente trava esperando ACK e não trata timeout. Como tornar assíncrono?" | Thread de recepção separada + FSM de envio. | A versão com `recvfrom` na mesma thread (da própria IA) foi descartada. | [LINK/ANEXO] |
| 5 | Concorrência | "Dá `dictionary changed size during iteration` de vez em quando. Por quê?" | Condição de corrida; `threading.Lock()`. | — | [LINK/ANEXO] |
| 6 | Correção da Entrega 1 | "o handshake de vocês conclui com SYN e SYN-ACK. O cliente recebe a resposta e encerra sem enviar o ACK final, e o servidor declara sucesso logo após o sendto, sem ter recebido confirmação" (feedback do monitor colado na conversa; pedimos a correção para atingir a nota máxima). | Handshake de 3 vias: estado `SYN_RCVD`, ISNs, ACK final validado, retransmissão de SYN e SYN-ACK por timer. | A IA havia gerado o handshake de 2 vias na Entrega 1 (Caso 1). Na correção, a revisão pegou também o `import random` local (Caso 2). | [LINK/ANEXO] |

## 4. Limites do uso da IA que adotamos
- A IA **não executa** nossa rede real: afirmações como "funciona" só valem depois de rodarmos os cenários do `manual_de_testes.txt`.
- Código gerado que não conseguimos explicar não entra no projeto.
- Feedback externo (monitor) foi tratado como parte do processo de revisão, e o erro do handshake foi registrado como falha da IA **e** nossa (aceitamos o código sem testar perdas no handshake).
