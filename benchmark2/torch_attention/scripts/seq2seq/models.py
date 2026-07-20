"""Model architectures for seq2seq translation.

Three encoder/decoder families are available and selectable by name:

* ``rnn``      - GRU encoder + plain GRU decoder (no attention).
* ``bahdanau`` - GRU encoder + additive (Bahdanau) attention decoder.
* ``luong``    - GRU encoder + multiplicative (Luong, general) attention decoder.

Every decoder returns ``(decoder_outputs, decoder_hidden, attentions)`` so the
training / evaluation code is architecture-agnostic. ``attentions`` is ``None``
for the plain RNN decoder.
"""
from __future__ import annotations

from typing import Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from .data import EOS_token, SOS_token  # noqa: F401 (EOS re-exported for convenience)

ARCHITECTURES = ("rnn", "bahdanau", "luong")

# Named hidden-size presets. "tiny" and "small" are used by the comparison
# script; "medium" reproduces the tutorial's default.
SIZE_PRESETS = {
    "tiny": 64,
    "small": 128,
    "medium": 256,
}


class EncoderRNN(nn.Module):
    def __init__(self, input_size: int, hidden_size: int, dropout_p: float = 0.1):
        super().__init__()
        self.hidden_size = hidden_size
        self.embedding = nn.Embedding(input_size, hidden_size)
        self.gru = nn.GRU(hidden_size, hidden_size, batch_first=True)
        self.dropout = nn.Dropout(dropout_p)

    def forward(self, input):
        embedded = self.dropout(self.embedding(input))
        output, hidden = self.gru(embedded)
        return output, hidden


class DecoderRNN(nn.Module):
    """Plain decoder that only consumes the encoder's final hidden state."""

    def __init__(
        self,
        hidden_size: int,
        output_size: int,
        max_length: int,
        device: torch.device,
        dropout_p: float = 0.1,
    ):
        super().__init__()
        self.max_length = max_length
        self.device = device
        self.embedding = nn.Embedding(output_size, hidden_size)
        self.gru = nn.GRU(hidden_size, hidden_size, batch_first=True)
        self.out = nn.Linear(hidden_size, output_size)

    def forward(self, encoder_outputs, encoder_hidden, target_tensor=None):
        batch_size = encoder_outputs.size(0)
        decoder_input = torch.empty(
            batch_size, 1, dtype=torch.long, device=self.device
        ).fill_(SOS_token)
        decoder_hidden = encoder_hidden
        decoder_outputs = []

        for i in range(self.max_length):
            decoder_output, decoder_hidden = self.forward_step(decoder_input, decoder_hidden)
            decoder_outputs.append(decoder_output)

            if target_tensor is not None:
                decoder_input = target_tensor[:, i].unsqueeze(1)  # teacher forcing
            else:
                _, topi = decoder_output.topk(1)
                decoder_input = topi.squeeze(-1).detach()

        decoder_outputs = torch.cat(decoder_outputs, dim=1)
        decoder_outputs = F.log_softmax(decoder_outputs, dim=-1)
        return decoder_outputs, decoder_hidden, None

    def forward_step(self, input, hidden):
        output = self.embedding(input)
        output = F.relu(output)
        output, hidden = self.gru(output, hidden)
        output = self.out(output)
        return output, hidden


class BahdanauAttention(nn.Module):
    """Additive attention (Bahdanau et al., 2015)."""

    def __init__(self, hidden_size: int):
        super().__init__()
        self.Wa = nn.Linear(hidden_size, hidden_size)
        self.Ua = nn.Linear(hidden_size, hidden_size)
        self.Va = nn.Linear(hidden_size, 1)

    def forward(self, query, keys):
        scores = self.Va(torch.tanh(self.Wa(query) + self.Ua(keys)))
        scores = scores.squeeze(2).unsqueeze(1)
        weights = F.softmax(scores, dim=-1)
        context = torch.bmm(weights, keys)
        return context, weights


class LuongAttention(nn.Module):
    """Multiplicative attention with the "general" score (Luong et al., 2015)."""

    def __init__(self, hidden_size: int):
        super().__init__()
        self.Wa = nn.Linear(hidden_size, hidden_size, bias=False)

    def forward(self, query, keys):
        # query: (B, 1, H), keys: (B, T, H)
        scores = torch.bmm(self.Wa(query), keys.transpose(1, 2))  # (B, 1, T)
        weights = F.softmax(scores, dim=-1)
        context = torch.bmm(weights, keys)  # (B, 1, H)
        return context, weights


class AttnDecoderRNN(nn.Module):
    """Attention decoder supporting Bahdanau or Luong attention."""

    def __init__(
        self,
        hidden_size: int,
        output_size: int,
        max_length: int,
        device: torch.device,
        attention: str = "bahdanau",
        dropout_p: float = 0.1,
    ):
        super().__init__()
        self.max_length = max_length
        self.device = device
        self.attention_kind = attention
        self.embedding = nn.Embedding(output_size, hidden_size)
        if attention == "bahdanau":
            self.attention: nn.Module = BahdanauAttention(hidden_size)
        elif attention == "luong":
            self.attention = LuongAttention(hidden_size)
        else:
            raise ValueError(f"Unknown attention kind: {attention}")
        self.gru = nn.GRU(2 * hidden_size, hidden_size, batch_first=True)
        self.out = nn.Linear(hidden_size, output_size)
        self.dropout = nn.Dropout(dropout_p)

    def forward(self, encoder_outputs, encoder_hidden, target_tensor=None):
        batch_size = encoder_outputs.size(0)
        decoder_input = torch.empty(
            batch_size, 1, dtype=torch.long, device=self.device
        ).fill_(SOS_token)
        decoder_hidden = encoder_hidden
        decoder_outputs = []
        attentions = []

        for i in range(self.max_length):
            decoder_output, decoder_hidden, attn_weights = self.forward_step(
                decoder_input, decoder_hidden, encoder_outputs
            )
            decoder_outputs.append(decoder_output)
            attentions.append(attn_weights)

            if target_tensor is not None:
                decoder_input = target_tensor[:, i].unsqueeze(1)  # teacher forcing
            else:
                _, topi = decoder_output.topk(1)
                decoder_input = topi.squeeze(-1).detach()

        decoder_outputs = torch.cat(decoder_outputs, dim=1)
        decoder_outputs = F.log_softmax(decoder_outputs, dim=-1)
        attentions = torch.cat(attentions, dim=1)
        return decoder_outputs, decoder_hidden, attentions

    def forward_step(self, input, hidden, encoder_outputs):
        embedded = self.dropout(self.embedding(input))
        query = hidden.permute(1, 0, 2)
        context, attn_weights = self.attention(query, encoder_outputs)
        input_gru = torch.cat((embedded, context), dim=2)
        output, hidden = self.gru(input_gru, hidden)
        output = self.out(output)
        return output, hidden, attn_weights


def resolve_hidden_size(size: Optional[str], hidden_size: Optional[int]) -> int:
    """Resolve a hidden size from an explicit value or a named preset."""
    if hidden_size is not None:
        return hidden_size
    if size is not None:
        if size not in SIZE_PRESETS:
            raise ValueError(
                f"Unknown size preset '{size}'. Choose from {list(SIZE_PRESETS)}."
            )
        return SIZE_PRESETS[size]
    return SIZE_PRESETS["medium"]


def build_model(
    arch: str,
    input_size: int,
    output_size: int,
    hidden_size: int,
    max_length: int,
    device: torch.device,
    dropout_p: float = 0.1,
) -> Tuple[nn.Module, nn.Module]:
    """Instantiate ``(encoder, decoder)`` for the requested architecture."""
    if arch not in ARCHITECTURES:
        raise ValueError(f"Unknown arch '{arch}'. Choose from {list(ARCHITECTURES)}.")

    encoder = EncoderRNN(input_size, hidden_size, dropout_p=dropout_p).to(device)

    if arch == "rnn":
        decoder: nn.Module = DecoderRNN(
            hidden_size, output_size, max_length, device, dropout_p=dropout_p
        )
    elif arch == "bahdanau":
        decoder = AttnDecoderRNN(
            hidden_size, output_size, max_length, device, attention="bahdanau", dropout_p=dropout_p
        )
    else:  # luong
        decoder = AttnDecoderRNN(
            hidden_size, output_size, max_length, device, attention="luong", dropout_p=dropout_p
        )

    return encoder, decoder.to(device)
