import struct

# ── Flags do protocolo ──────────────────────────────────────────────────────
FLAG_SYN  = 1 << 0   # Inicia conexão
FLAG_ACK  = 1 << 1   # Confirmação positiva
FLAG_FIN  = 1 << 3   # Encerramento
FLAG_DATA = 1 << 4   # Pacote de dados

# ── Modos de operação ────────────────────────────────────────────────────────
MODE_GBN = 0   # Go-Back-N
MODE_SR  = 1   # Selective Repeat

# ── Tamanho máximo de payload por fragmento ──────────────────────────────────
MAX_PAYLOAD_SIZE = 4   # <= 4 bytes por fragmento (exigência do enunciado)

# ── Formato do cabeçalho binário ─────────────────────────────────────────────
# ! = big-endian (rede)
# H = 2 bytes sem sinal  |  B = 1 byte sem sinal
# campos: seq_num(2) | ack_num(2) | flags(1) | mode(1) | window_size(2) | max_text_size(2)
HEADER_FORMAT = "!H H B B H H"
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)


class Packet:
    """Pacote do protocolo TCD – Checkpoint 2.

    Campos:
        seq_num       – número de sequência do pacote de dados
        ack_num       – número sendo confirmado (ACK)
        flags         – combinação de FLAG_*
        mode          – MODE_GBN ou MODE_SR
        window_size   – tamanho da janela (negociado no handshake)
        max_text_size – tamanho máximo da mensagem (negociado no handshake)
        payload       – dados transportados (até MAX_PAYLOAD_SIZE bytes)
    """

    def __init__(self, seq_num=0, ack_num=0, flags=0,
                 mode=MODE_GBN, window_size=5, max_text_size=30, payload=b""):
        self.seq_num       = seq_num
        self.ack_num       = ack_num
        self.flags         = flags
        self.mode          = mode
        self.window_size   = window_size
        self.max_text_size = max_text_size
        self.payload       = payload

    # ── serialização ──────────────────────────────────────────────────────────
    def to_bytes(self) -> bytes:
        header = struct.pack(
            HEADER_FORMAT,
            self.seq_num,
            self.ack_num,
            self.flags,
            self.mode,
            self.window_size,
            self.max_text_size,
        )
        return header + self.payload

    # ── desserialização ───────────────────────────────────────────────────────
    @classmethod
    def from_bytes(cls, data: bytes) -> "Packet":
        if len(data) < HEADER_SIZE:
            raise ValueError("Pacote menor que o cabeçalho esperado.")
        seq_num, ack_num, flags, mode, window_size, max_text_size = struct.unpack(
            HEADER_FORMAT, data[:HEADER_SIZE]
        )
        payload = data[HEADER_SIZE:]
        return cls(seq_num, ack_num, flags, mode, window_size, max_text_size, payload)

    # ── representação legível ─────────────────────────────────────────────────
    def __str__(self) -> str:
        flags_str = []
        if self.flags & FLAG_SYN:  flags_str.append("SYN")
        if self.flags & FLAG_ACK:  flags_str.append("ACK")
        if self.flags & FLAG_FIN:  flags_str.append("FIN")
        if self.flags & FLAG_DATA: flags_str.append("DATA")
        mode_str = "SR" if self.mode == MODE_SR else "GBN"
        return (
            f"[Packet SEQ={self.seq_num} ACK={self.ack_num} "
            f"FLAGS={'|'.join(flags_str) or 'NONE'} MODE={mode_str} "
            f"WIN={self.window_size} MAX_TEXT={self.max_text_size} "
            f"PAYLOAD={self.payload}]"
        )
