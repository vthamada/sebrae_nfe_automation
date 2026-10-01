import re
from decimal import Decimal, InvalidOperation


_DECIMAL_PATTERN = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
_MAX_MONEY = Decimal("999999999999.99")
_MAX_QUANTITY = Decimal("999999999.999")


def normalize_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).strip().upper().split())


def _scalar_text(value):
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def digits_only(value):
    return re.sub(r"\D", "", _scalar_text(value))


def normalize_document(value):
    return digits_only(value)


def _parse_decimal(value):
    if isinstance(value, Decimal):
        parsed = value
    else:
        text = _scalar_text(value).replace("R$", "").replace(" ", "")
        if not text:
            raise ValueError("Valor numérico obrigatório.")
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        if not _DECIMAL_PATTERN.fullmatch(text):
            raise ValueError("Formato numérico inválido.")
        try:
            parsed = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("Formato numérico inválido.") from exc
    if not parsed.is_finite():
        raise ValueError("O valor deve ser finito.")
    return parsed


def money_to_cents(value):
    parsed = _parse_decimal(value)
    if parsed < 0 or parsed > _MAX_MONEY:
        raise ValueError("Valor monetário fora do intervalo permitido.")
    scaled = parsed * 100
    if scaled != scaled.to_integral_value():
        raise ValueError("Valor monetário deve ter no máximo 2 casas decimais.")
    return int(scaled)


def quantity_to_milli(value, *, allow_zero=False, allow_negative=False):
    parsed = _parse_decimal(value)
    if abs(parsed) > _MAX_QUANTITY:
        raise ValueError("Quantidade fora do intervalo permitido.")
    if not allow_negative and parsed < 0:
        raise ValueError("Quantidade não pode ser negativa.")
    if not allow_zero and parsed == 0:
        raise ValueError("Quantidade deve ser maior que zero.")
    scaled = parsed * 1000
    if scaled != scaled.to_integral_value():
        raise ValueError("Quantidade deve ter no máximo 3 casas decimais.")
    return int(scaled)


def format_money(cents):
    return f"{Decimal(int(cents)) / 100:.2f}"


def format_quantity(milliunits):
    return f"{Decimal(int(milliunits)) / 1000:.3f}"


def validate_money(value):
    try:
        money_to_cents(value)
        return True
    except (TypeError, ValueError, InvalidOperation):
        return False


def validate_ncm(ncm):
    if ncm in (None, ""):
        return True
    return len(digits_only(ncm)) == 8


def validate_cest(cest):
    if cest in (None, ""):
        return True
    return len(digits_only(cest)) == 7


def validate_cfop(cfop):
    if cfop in (None, ""):
        return True
    return len(digits_only(cfop)) == 4


def validate_tags(tags):
    if not tags:
        return True, []
    if isinstance(tags, (list, tuple, set)):
        parts = [str(part).strip() for part in tags if str(part).strip()]
    else:
        parts = [part.strip() for part in re.split(r"[;,]", str(tags)) if part.strip()]
    bad = [part for part in parts if len(part) < 3]
    return not bad, bad


def validate_document(document):
    digits = normalize_document(document)
    if len(digits) == 11:
        if digits == digits[0] * 11:
            return False
        numbers = [int(char) for char in digits]
        first = (sum(numbers[index] * (10 - index) for index in range(9)) * 10) % 11
        first = 0 if first == 10 else first
        second = (sum(numbers[index] * (11 - index) for index in range(10)) * 10) % 11
        second = 0 if second == 10 else second
        return numbers[9:] == [first, second]
    if len(digits) == 14:
        if digits == digits[0] * 14:
            return False
        numbers = [int(char) for char in digits]

        def digit(values, weights):
            remainder = sum(value * weight for value, weight in zip(values, weights)) % 11
            return 0 if remainder < 2 else 11 - remainder

        first = digit(numbers[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        second = digit(numbers[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        return numbers[12:] == [first, second]
    return False


def validate_nfe_access_key(value):
    key = digits_only(value)
    if len(key) != 44:
        return False
    weight = 2
    total = 0
    for char in reversed(key[:43]):
        total += int(char) * weight
        weight = 2 if weight == 9 else weight + 1
    check_digit = 11 - (total % 11)
    if check_digit >= 10:
        check_digit = 0
    return int(key[-1]) == check_digit


def validate_product(product):
    errors = []
    if not normalize_text(product.get("description")):
        errors.append("Descrição obrigatória.")
    if not normalize_text(product.get("internal_code")):
        errors.append("Código interno obrigatório.")
    if not normalize_text(product.get("unit")):
        errors.append("Unidade obrigatória.")
    if not validate_ncm(product.get("ncm")):
        errors.append("NCM deve possuir 8 dígitos.")
    if not validate_cest(product.get("cest")):
        errors.append("CEST deve possuir 7 dígitos.")
    if not validate_cfop(product.get("cfop")):
        errors.append("CFOP deve possuir 4 dígitos.")
    ok, bad = validate_tags(product.get("tags"))
    if not ok:
        errors.append("Tags com menos de 3 caracteres: " + ", ".join(bad))
    for field in ("cost_price", "sale_price"):
        if not validate_money(product.get(field, 0)):
            errors.append(f"{field} inválido.")
    for field in ("stock_qty", "min_stock"):
        try:
            quantity_to_milli(product.get(field, 0), allow_zero=True)
        except ValueError:
            errors.append(f"{field} inválido.")
    return errors


def validate_customer(customer):
    errors = []
    if not validate_document(customer.get("document")):
        errors.append("CPF ou CNPJ inválido.")
    if not normalize_text(customer.get("legal_name")):
        errors.append("Razão social ou nome obrigatório.")
    state = normalize_text(customer.get("state"))
    if state and (len(state) != 2 or not state.isalpha()):
        errors.append("UF deve possuir 2 letras.")
    email = str(customer.get("email") or "").strip()
    if email and ("@" not in email or email.startswith("@") or email.endswith("@")):
        errors.append("E-mail inválido.")
    return errors
