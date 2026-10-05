with open("api/main.py") as f:
    text = f.read()

text = text.replace(
    '{"product_type": "credit_card"|"loan"|null,\\n "requested_amount": float|null, "currency": "USD"|"EUR"|null}',
    '{"product_type": "Tarjeta Crédito"|"Préstamo Personal"|"Préstamo Hipotecario"|null,\\n "requested_amount": float|null, "currency": "USD"|"EUR"|null}',
)

with open("api/main.py", "w") as f:
    f.write(text)
