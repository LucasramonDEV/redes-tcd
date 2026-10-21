import struct

# ── Flags do protocolo ──────────────────────────────────────────────────────
FLAG_SYN  = 1 << 0   # Inicia conexão
FLAG_ACK  = 1 << 1   # Confirmação

# ── Modos de operação ────────────────────────────────────────────────────────
MODE_GBN = 0   # Go-Back-N
MODE_SR  = 1   # Selective Repeat

# ── Formato do cabeçalho binário ─────────────────────────────────────────────
# ! = big-endian (rede)
# B = 1 byte sem sinal
# H = 2 bytes sem sinal
# campos: flags(1) | mode(1) | window_size(2) | max_text_size(2)
HEADER_FORMAT = "!B B H H"
HEADER_SIZE   = struct.calcsize(HEADER_FORMAT)


class Packet:
    """Pacote do handshake inicial (Checkpoint 1).

    Campos:
        flags         – FLAG_SYN ou FLAG_ACK ou ambos
        mode          – MODE_GBN (0) ou MODE_SR (1)
        window_size   – tamanho da janela de recepção definido pelo servidor
        max_text_size – limite máximo (em bytes) da mensagem do usuário
    """

    def __init__(self, flags=0, mode=MODE_GBN, window_size=0, max_text_size=0):
        self.flags         = flags
        self.mode          = mode
        self.window_size   = window_size
        self.max_text_size = max_text_size

    # ── serialização ──────────────────────────────────────────────────────────
    def to_bytes(self) -> bytes:
        return struct.pack(
            HEADER_FORMAT,
            self.flags,
            self.mode,
            self.window_size,
            self.max_text_size,
        )

    # ── desserialização ───────────────────────────────────────────────────────
    @classmethod
    def from_bytes(cls, data: bytes) -> "Packet":
        if len(data) < HEADER_SIZE:
            raise ValueError("Pacote menor que o cabeçalho esperado.")
        flags, mode, window_size, max_text_size = struct.unpack(
            HEADER_FORMAT, data[:HEADER_SIZE]
        )
        return cls(flags, mode, window_size, max_text_size)

    # ── representação legível ─────────────────────────────────────────────────
    def __str__(self) -> str:
        flags_str = []
        if self.flags & FLAG_SYN: flags_str.append("SYN")
        if self.flags & FLAG_ACK: flags_str.append("ACK")
        mode_str = "SR" if self.mode == MODE_SR else "GBN"
        return (
            f"[Packet FLAGS={'|'.join(flags_str) or 'NONE'} "
            f"MODE={mode_str} WIN={self.window_size} "
            f"MAX_TEXT={self.max_text_size}]"
        )
