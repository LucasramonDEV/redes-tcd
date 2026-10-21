# Relatório – Checkpoint 2: Protocolo Sem Erros
## Trabalho I – Redes de Computadores

---

## O que foi entregue

Implementação completa do protocolo TCD sobre canal **sem erros e sem perdas**, incluindo:

1. **Handshake** (herdado do CP1) — troca de modo, janela e max_text
2. **Fragmentação** — mensagem quebrada em pedaços de ≤ 4 bytes
3. **Envio com janela deslizante** — Go-Back-N (GBN) ou Selective Repeat (SR)
4. **ACK por fragmento** — servidor confirma cada fragmento recebido
5. **Encerramento** — cliente envia FIN, servidor responde FIN-ACK

---

## Fluxo completo do protocolo

```
Cliente                                  Servidor
   |--- SYN (modo, max_text) ----------->|
   |<-- SYN-ACK (modo, janela, max_text)-|
   |                                     |
   |--- DATA SEQ=0 "Hell" -------------->|
   |--- DATA SEQ=1 "o Wo" -------------->|  ← envia até window_size sem esperar
   |--- DATA SEQ=2 "rld!" -------------->|
   |<-- ACK 0 ---------------------------|
   |<-- ACK 1 ---------------------------|
   |<-- ACK 2 ---------------------------|
   |                                     |
   |--- FIN ----------------------------->|
   |<-- FIN-ACK --------------------------|
```

---

## O que estudar para responder ao monitor

### 1. O que é fragmentação e por que fragmentar em 4 bytes?

Mensagens grandes precisam ser quebradas em **fragmentos menores** para:
- Respeitar limites do buffer de rede
- Permitir retransmissão seletiva (só o fragmento com erro, não a mensagem toda)
- Simular o comportamento real de protocolos como TCP, que também fragmenta

No nosso protocolo: `payload ≤ 4 bytes por fragmento` (exigência do enunciado).

Exemplo: `"Hello World"` → `["Hell", "o Wo", "rld!"]` → 3 fragmentos com SEQ 0, 1, 2.

### 2. O que é número de sequência?

Cada fragmento tem um **SEQ** (número de sequência) que permite ao servidor:
- Identificar qual fragmento chegou
- Detectar duplicatas
- Reordenar fragmentos fora de ordem (SR)

No nosso protocolo SEQ começa em 0 e incrementa +1 por fragmento.

### 3. O que é janela deslizante?

Em vez de enviar 1 fragmento, esperar ACK, enviar o próximo (lento), a janela deslizante permite enviar **N fragmentos de uma vez** sem esperar confirmação:

```
Janela = 5:

Fragmentos: [0][1][2][3][4] [5][6][7]...
             |←   janela  →|
             base           base+5

→ Envia 0,1,2,3,4 de uma vez
→ Recebe ACK 0 → janela desliza → envia 5
→ Recebe ACK 1 → janela desliza → envia 6
```

### 4. Go-Back-N vs Selective Repeat (diferenças práticas)

| Situação            | Go-Back-N                          | Selective Repeat                   |
|---------------------|------------------------------------|------------------------------------|
| Fragmento na ordem  | Aceita, envia ACK                  | Aceita, envia ACK                  |
| Fragmento fora ordem| **Descarta**, reenvía último ACK   | **Guarda no buffer**, envia ACK    |
| Timeout             | Reenvia **toda a janela**          | Reenvia **só o que venceu**        |
| Complexidade        | Simples                            | Mais complexo (buffer no receptor) |
| Eficiência          | Menor (muita retransmissão)        | Maior (só retransmite o necessário)|

**No CP2 (sem erros):** ambos se comportam igual — todos chegam na ordem, todos são aceitos. A diferença aparece no CP3 quando introduzimos erros e perdas.

### 5. O que é ACK (Acknowledgement)?

É a **confirmação** que o servidor envia ao cliente para dizer "recebi o fragmento N com sucesso". Sem ACK, o cliente não sabe se o fragmento chegou.

- **GBN:** ACK N significa "recebi tudo até N" (cumulativo)
- **SR:** ACK N significa "recebi especificamente o fragmento N" (individual)

### 6. O que é timeout e por que existe no CP2?

Mesmo sem erros, mantemos o timeout como **mecanismo de segurança** da máquina de estados. Se por algum motivo o ACK demorar mais que `TIMEOUT = 2.0s`, o cliente retransmite.

No CP2 (canal perfeito) o timeout nunca deve disparar — mas o código precisa existir para o CP3.

### 7. O que é o FIN / FIN-ACK?

É o **encerramento formal** da conexão:
- Cliente envia `FIN` dizendo "terminei de enviar"
- Servidor imprime a mensagem completa e responde `FIN-ACK`
- Cliente fecha o socket

Isso evita que o servidor fique esperando mais dados indefinidamente.

### 8. Por que usamos threads no cliente?

O cliente precisa fazer duas coisas **ao mesmo tempo**:
- Enviar fragmentos (loop principal)
- Receber ACKs do servidor (loop separado)

Se fizesse as duas coisas sequencialmente, travaria esperando um ACK antes de enviar o próximo, perdendo toda a vantagem da janela deslizante.

A solução: `threading.Thread` para a recepção em paralelo, com `threading.Lock` para evitar que as duas threads modifiquem o estado ao mesmo tempo.

---

## Como testar

```bash
# Terminal 1
python server.py --port 12000

# Terminal 2 – GBN
python client.py --server 127.0.0.1 --port 12000 --mode gbn

# Terminal 2 – SR
python client.py --server 127.0.0.1 --port 12000 --mode sr
```

**Exemplo de saída (GBN, mensagem "Hello World"):**
```
[*] Enviando SYN...
[*] Handshake OK – janela=5 max_text=30

Digite a mensagem (máx 30 chars): Hello World
[*] 3 fragmento(s) para enviar.

[ENVIADO] SEQ=0 payload='Hell'
[ENVIADO] SEQ=1 payload='o Wo'
[ENVIADO] SEQ=2 payload='rld!'
[RECEBIDO] ACK 0
[RECEBIDO] ACK 1
[RECEBIDO] ACK 2

[*] Todos os fragmentos confirmados!
[*] FIN enviado. Aguardando FIN-ACK...
[*] Conexão encerrada pelo servidor.
```

---

## Resumo das escolhas de projeto

| Decisão                    | Escolha              | Motivo                                           |
|----------------------------|----------------------|--------------------------------------------------|
| Payload máximo             | 4 bytes              | Exigência do enunciado                           |
| SEQ começa em              | 0                    | Convencional                                     |
| Thread separada p/ recepção| Sim                  | Necessário para janela deslizante funcionar      |
| Timeout no CP2             | 2 segundos           | Segurança; nunca dispara em canal sem erros      |
| GBN – ACK cumulativo       | Sim                  | Padrão do algoritmo GBN                         |
| SR – buffer no receptor    | Sim (dict por seq)   | Permite reordenar fragmentos fora de ordem       |
