"""ADR-0001 — parser de .vcf do renomeador de contatos.

Cobre o módulo puro `app.application.contacts.vcf`: remoção do código legado,
extração de endereço do padrão de nome da revenda, leitura de `ADR`/`NOTE` e a
precedência ADR > NOTE > nome legado.
"""

from app.application.contacts.vcf import (
    normalize_cep,
    parse_adr,
    parse_legacy_name,
    parse_note,
    parse_vcf,
    strip_legacy_code,
)


# ═══════════════════════════════════════════════════════════
# normalize_cep
# ═══════════════════════════════════════════════════════════


class TestNormalizeCep:
    def test_formats_eight_digits(self):
        assert normalize_cep("00000000") == "00000-000"
        assert normalize_cep("01310-100") == "01310-100"
        assert normalize_cep("01310 100") == "01310-100"

    def test_rejects_wrong_length(self):
        assert normalize_cep("123") is None
        assert normalize_cep("") is None
        assert normalize_cep(None) is None


# ═══════════════════════════════════════════════════════════
# strip_legacy_code
# ═══════════════════════════════════════════════════════════


class TestStripLegacyCode:
    def test_removes_numeric_code_prefix(self):
        assert strip_legacy_code("114= rua X Nº10") == "rua X Nº10"
        assert strip_legacy_code("000145= João Souza") == "João Souza"
        assert strip_legacy_code("  12 = Maria") == "Maria"

    def test_plain_name_untouched(self):
        assert strip_legacy_code("João Souza") == "João Souza"
        assert strip_legacy_code("") == ""

    def test_never_destroys_a_name_that_is_only_the_code(self):
        assert strip_legacy_code("114=") == "114="


# ═══════════════════════════════════════════════════════════
# parse_legacy_name
# ═══════════════════════════════════════════════════════════


class TestParseLegacyName:
    def test_full_pattern_from_the_client_example(self):
        parsed = parse_legacy_name("1= berredos Nº 145 entre Rua A e Rua B - CEP 00000-000")
        assert parsed == {
            "rua": "berredos",
            "numero": "145",
            "entre_ruas": "Rua A e Rua B",
            "cep": "00000-000",
        }

    def test_without_entre_and_cep(self):
        assert parse_legacy_name("114= rua X Nº10") == {"rua": "rua X", "numero": "10"}

    def test_without_numero(self):
        assert parse_legacy_name("114= rua X") == {"rua": "rua X"}

    def test_only_entre(self):
        assert parse_legacy_name("7= Rua das Flores entre Rua A e Rua B") == {
            "rua": "Rua das Flores",
            "entre_ruas": "Rua A e Rua B",
        }

    def test_returns_none_when_not_the_legacy_pattern(self):
        assert parse_legacy_name("João Souza") is None
        assert parse_legacy_name("114=") is None
        assert parse_legacy_name(None) is None

    # ── Fase 2 §8.5: exemplos literais do cliente (obrigatórios) ──

    def test_literal_example_1443_berredos(self):
        """`1443= berredos 145` → rua/número (número solto no fim)."""
        assert parse_legacy_name("1443= berredos 145") == {"rua": "berredos", "numero": "145"}

    def test_literal_example_1_berredos_completo(self):
        """`1= berredos Nº 145 entre Rua A e Rua B - CEP 00000-000`."""
        assert parse_legacy_name("1= berredos Nº 145 entre Rua A e Rua B - CEP 00000-000") == {
            "rua": "berredos",
            "numero": "145",
            "entre_ruas": "Rua A e Rua B",
            "cep": "00000-000",
        }

    def test_bare_number_needs_a_real_street(self):
        # Guarda do número solto: remanescente que é só o tipo da via não conta.
        assert parse_legacy_name("5= Rua 25") == {"rua": "Rua 25"}

    def test_recovers_person_from_the_renamer_output(self):
        # Reimportar a própria saída (D5) não perde a pessoa.
        parsed = parse_legacy_name("1= berredos Nº 145 entre Rua A e Rua B - CEP 00000-000 (João)")
        assert parsed == {
            "rua": "berredos",
            "numero": "145",
            "entre_ruas": "Rua A e Rua B",
            "cep": "00000-000",
        }


# ═══════════════════════════════════════════════════════════
# parse_adr
# ═══════════════════════════════════════════════════════════


class TestParseAdr:
    def test_reads_spec_order(self):
        # pobox;ext;rua;cidade;região;CEP;país
        parsed = parse_adr(";;Rua das Flores, 145;Centro;;01310-100;")
        assert parsed == {
            "rua": "Rua das Flores",
            "numero": "145",
            "bairro": "Centro",
            "cep": "01310-100",
        }

    def test_keeps_complemento(self):
        parsed = parse_adr(";;Rua das Flores Nº 145;Centro;;01310-100;Brasil")
        assert parsed["rua"] == "Rua das Flores"
        assert parsed["numero"] == "145"

    def test_empty_returns_empty_dict(self):
        assert parse_adr("") == {}
        assert parse_adr(None) == {}


# ═══════════════════════════════════════════════════════════
# parse_note
# ═══════════════════════════════════════════════════════════


class TestParseNote:
    def test_extracts_entre_and_cep(self):
        parsed = parse_note("Portão azul — entre Rua A e Rua B. CEP 00000-000")
        assert parsed["entre_ruas"] == "Rua A e Rua B"
        assert parsed["cep"] == "00000-000"

    def test_ignores_time_range(self):
        # "entre 14h e 18h" é horário, não rua.
        assert parse_note("Ligar entre 14h e 18h") == {}

    def test_empty(self):
        assert parse_note("") == {}
        assert parse_note(None) == {}


# ═══════════════════════════════════════════════════════════
# parse_vcf
# ═══════════════════════════════════════════════════════════


LEGACY_CARD = """\
BEGIN:VCARD
VERSION:3.0
FN:114= rua X Nº10 entre Rua A e Rua B - CEP 00000-000
TEL;TYPE=CELL:+5511999990000
END:VCARD
"""

ADR_CARD = """\
BEGIN:VCARD
VERSION:3.0
FN:Maria Silva
TEL;TYPE=CELL:+5511999990001
ADR;TYPE=HOME:;;Rua das Flores, 145;Centro;;01310-100;Brasil
NOTE:Portão azul
END:VCARD
"""


class TestParseVcf:
    def test_legacy_name_becomes_structured_address(self):
        contacts = parse_vcf(LEGACY_CARD)
        assert len(contacts) == 1
        contact = contacts[0]
        assert contact["telefone"] == "+5511999990000"
        # §8.3: o padrão legado é ENDEREÇO, não pessoa — o bruto vai p/ nome_importado.
        assert contact["nome"] is None
        assert contact["nome_importado"] == "114= rua X Nº10 entre Rua A e Rua B - CEP 00000-000"
        assert contact["rua"] == "rua X"
        assert contact["numero"] == "10"
        assert contact["entre_ruas"] == "Rua A e Rua B"
        assert contact["cep"] == "00000-000"

    def test_adr_wins_over_the_name(self):
        contacts = parse_vcf(ADR_CARD)
        contact = contacts[0]
        assert contact["nome"] == "Maria Silva"
        assert contact["rua"] == "Rua das Flores"
        assert contact["numero"] == "145"
        assert contact["bairro"] == "Centro"
        assert contact["cep"] == "01310-100"

    def test_multiple_tels_become_one_contact_with_secondary(self):
        """§8.4: 1º TEL = principal, 2º = telefone_secundario (não duplica cliente)."""
        raw = """\
BEGIN:VCARD
FN:João
TEL;TYPE=CELL:+5511999990002
TEL;TYPE=HOME:+551133334444
END:VCARD
"""
        contacts = parse_vcf(raw)
        assert len(contacts) == 1
        assert contacts[0]["telefone"] == "+5511999990002"
        assert contacts[0]["telefone_secundario"] == "+551133334444"
        assert contacts[0]["telefones_ignorados"] == 0
        assert contacts[0]["nome"] == "João"

    def test_extra_tels_are_counted_never_silently_dropped(self):
        raw = """\
BEGIN:VCARD
FN:João
TEL:+5511999990002
TEL:+551133334444
TEL:+551122223333
END:VCARD
"""
        contacts = parse_vcf(raw)
        assert len(contacts) == 1
        assert contacts[0]["telefones_ignorados"] == 1

    def test_card_without_tel_is_skipped(self):
        raw = "BEGIN:VCARD\nFN:Sem Telefone\nEND:VCARD\n"
        assert parse_vcf(raw) == []

    def test_falls_back_to_n_when_fn_missing(self):
        raw = "BEGIN:VCARD\nN:Souza;João;;;\nTEL:+5511999990003\nEND:VCARD\n"
        assert parse_vcf(raw)[0]["nome"] == "João Souza"

    def test_note_fills_cep_when_adr_absent(self):
        raw = """\
BEGIN:VCARD
FN:Pedro
TEL:+5511999990004
NOTE:CEP 00000-000
END:VCARD
"""
        assert parse_vcf(raw)[0]["cep"] == "00000-000"

    def test_empty_input(self):
        assert parse_vcf("") == []


# ═══════════════════════════════════════════════════════════
# vCard real: folding, QUOTED-PRINTABLE, `\;` escapado (§8.2)
# ═══════════════════════════════════════════════════════════


class TestVCardRobustness:
    def test_line_folding_is_joined(self):
        raw = "BEGIN:VCARD\nFN:Maria Si\n lva\nTEL:+5511999990005\nEND:VCARD\n"
        assert parse_vcf(raw)[0]["nome"] == "Maria Silva"

    def test_quoted_printable_with_charset(self):
        # "João" em QP/latin-1 → J=6F=E3o (NÃO usar J=6F aqui: '=' = 3D).
        raw = (
            "BEGIN:VCARD\n"
            "FN;CHARSET=ISO-8859-1;ENCODING=QUOTED-PRINTABLE:Jo=E3o\n"
            "TEL:+5511999990006\n"
            "END:VCARD\n"
        )
        assert parse_vcf(raw)[0]["nome"] == "João"

    def test_escaped_semicolon_in_adr_does_not_split(self):
        raw = (
            "BEGIN:VCARD\nFN:Ana\n"
            "ADR;TYPE=HOME:;;Rua A\\; B, 10;Centro;;00000-000;Brasil\n"
            "TEL:+5511999990007\nEND:VCARD\n"
        )
        contact = parse_vcf(raw)[0]
        assert contact["rua"] == "Rua A; B"
        assert contact["numero"] == "10"
        assert contact["bairro"] == "Centro"
        assert contact["cep"] == "00000-000"

    def test_person_name_survives_the_legacy_address_pattern(self):
        raw = "BEGIN:VCARD\n" "FN:1443= berredos 145 (João)\n" "TEL:+5511999990008\n" "END:VCARD\n"
        contact = parse_vcf(raw)[0]
        assert contact["nome"] == "João"
        assert contact["rua"] == "berredos"
        assert contact["numero"] == "145"
        assert contact["nome_importado"] == "1443= berredos 145 (João)"
