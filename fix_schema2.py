import re

with open("api/main.py") as f:
    text = f.read()

text = re.sub(
    r'\{\{"product_type": "credit_card"\|"loan"\|null,(.*?)\}\}',
    r'{{"product_type": "Tarjeta Crédito"|"Préstamo Personal"|"Préstamo Hipotecario"|null,\1}}',
    text,
    flags=re.DOTALL,
)

with open("api/main.py", "w") as f:
    f.write(text)
