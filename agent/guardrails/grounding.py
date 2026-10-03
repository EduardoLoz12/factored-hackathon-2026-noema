"""GroundingChecker: ninguna cifra sale del modelo — AG-09.

Es la regla 1 del proyecto hecha máquina. Extrae los números y los datos personales de
la respuesta final y comprueba que cada uno exista entre los valores que devolvieron los
tools **de ese turno**. Un valor huérfano bloquea la respuesta; al segundo intento
fallido, se escala (`docs/05_security.md` §4).

Sin esto, «el modelo no inventa cifras» es una promesa. Con esto es una propiedad
verificable y medible.

## Por qué no se pueden comparar flotantes

El motor interpola las cifras **formateadas**, y el formato las transforma:

| Hecho | Lo que el cliente lee |
|---|---|
| `dti_actual = 3.375` | «el **338%** de tu ingreso» |
| `dti_corte_duro = 0.6` | «el límite de **60%**» |
| `carga_mensual_usd = 1234.56` | «**1,235** USD» |

Buscar 3.375 en «338%» no encuentra nada. Así que el checker **genera los renderizados
posibles de cada valor anclado** y compara textos. Es exacto: no arrastra el error de
volver a parsear lo que ya se formateó.

## Las dos ambigüedades que hay que admitir

1. **El porcentaje no dice su escala.** «40%» puede venir de `0.40` o de `40`. Admitir
   solo una lectura produciría falsos positivos que bloquean respuestas correctas, y un
   guardrail que bloquea lo correcto se termina apagando.
2. **El separador de miles depende de la convención.** `{:,.0f}` produce «1,235», que en
   es-CO y es-AR se lee como *uno coma dos*. El checker acepta las dos convenciones, para
   que si algún día se corrige el formato de los mensajes no haya que tocar el guardrail.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)

# Tolerancia relativa al cotejar por valor, no por texto. Absorbe el redondeo del
# formateo —«338%» viene de 3.375— sin admitir una cifra distinta.
TOLERANCIA_RELATIVA = 0.005

# Fechas completas primero: si no, «2025-12-31» se partiría en tres números huérfanos.
FECHA = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# Número con separadores opcionales y porcentaje opcional.
#
# El `+` en el grupo de miles no es cosmético: con `*`, la alternancia probaba primero la
# forma agrupada y «9000» se leía como «900», dejando el «0» suelto. Una cifra
# correctamente anclada parecía inventada — el falso positivo que hace que un guardrail
# se termine apagando. Con `+`, la primera alternativa exige al menos un separador y
# «9000» cae a la segunda, que lo toma entero.
NUMERO = re.compile(r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*(%?)")
CORREO = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
# Secuencias largas de dígitos: documentos, tarjetas. Ocho o más seguidos sin separador.
DIGITOS_LARGOS = re.compile(r"(?<!\d)\d{8,}(?!\d)")

# Números que no son una afirmación sobre el cliente y aparecen en prosa corriente.
# Mantener la lista corta: cada entrada es un agujero, y uno largo vacía el guardrail.
TOLERADOS = frozenset({"0", "1", "2"})


@dataclass(frozen=True)
class Huerfana:
    """Una cifra de la respuesta que ningún tool respalda."""

    texto: str
    posicion: int
    es_porcentaje: bool = False

    def __str__(self) -> str:  # pragma: no cover - solo para mensajes
        return f"«{self.texto}»"


@dataclass
class Resultado:
    """Veredicto del checker. `ok` es False si queda una sola cifra sin anclaje."""

    ok: bool
    huerfanas: tuple[Huerfana, ...] = ()
    cifras_citadas: int = 0
    cifras_ancladas: int = 0
    pii_detectada: tuple[str, ...] = ()

    @property
    def motivo(self) -> str | None:
        if self.pii_detectada:
            return "pii_sin_respaldo"
        if self.huerfanas:
            return "cifra_sin_anclaje"
        return None

    def a_traza(self) -> dict[str, Any]:
        """Sin los valores: la traza no necesita repetir las cifras del cliente."""
        return {
            "etapa": "VERIFY",
            "control": "grounding",
            "ok": self.ok,
            "motivo": self.motivo,
            "cifras_citadas": self.cifras_citadas,
            "cifras_ancladas": self.cifras_ancladas,
            "n_huerfanas": len(self.huerfanas),
            "n_pii": len(self.pii_detectada),
        }


def _sin_separadores(token: str) -> set[float]:
    """Lecturas numéricas posibles de un token, con las dos convenciones de separador.

    «1,200» es mil doscientos en inglés y uno coma dos en español. Las dos se admiten:
    el checker no decide la convención, solo comprueba el anclaje.
    """
    lecturas: set[float] = set()
    for miles, decimal in ((",", "."), (".", ",")):
        limpio = token.replace(miles, "")
        if decimal != ".":
            limpio = limpio.replace(decimal, ".")
        try:
            lecturas.add(float(limpio))
        except ValueError:
            continue
    try:
        lecturas.add(float(token.replace(",", "")))
    except ValueError:
        pass
    return lecturas


def renderizados(valor: float) -> set[str]:
    """Todas las formas en que un valor anclado puede aparecer en la respuesta.

    Son los formatos que el motor usa de verdad: porcentaje con cero y un decimal,
    miles con cero y dos decimales, y el valor crudo. Más sus equivalentes con la
    convención de separadores invertida.
    """
    formas: set[str] = set()
    plantillas = ("{:.0%}", "{:.1%}", "{:,.0f}", "{:,.2f}", "{:.0f}", "{:.1f}", "{:.2f}", "{:.4f}")
    for plantilla in plantillas:
        try:
            formas.add(plantilla.format(valor).rstrip("%"))
        except (ValueError, TypeError):
            continue
    formas.add(str(valor))
    if float(valor).is_integer():
        formas.add(str(int(valor)))
    # La misma cifra con la convención española de separadores.
    for forma in list(formas):
        if "," in forma or "." in forma:
            formas.add(forma.replace(",", "\x00").replace(".", ",").replace("\x00", "."))
    # Sin separadores de miles, que es como el modelo puede reescribirla.
    for forma in list(formas):
        formas.add(forma.replace(",", ""))
    return formas


@dataclass
class GroundingChecker:
    """Comprueba que toda cifra de la respuesta venga de un tool de ese turno."""

    # Contadores para `EV-06`. Por respuesta revisada, no por turno.
    revisadas: int = 0
    bloqueadas: int = 0
    _historial: list[Resultado] = field(default_factory=list, repr=False)

    def revisar(
        self,
        texto: str,
        *,
        valores: list[Any] | tuple[Any, ...],
        textos: list[str] | tuple[str, ...] = (),
        umbrales: list[Any] | tuple[Any, ...] = (),
    ) -> Resultado:
        """Revisa una respuesta.

        `valores` son las cifras que los tools devolvieron en el turno. `umbrales` son
        los de la política: un motivo honesto dice **dos** cifras —la del cliente y la
        que debía alcanzar— y la segunda es política, no cliente. `textos` admite las
        cadenas ancladas, como la fecha de corte.
        """
        self.revisadas += 1
        anclados = [
            float(v)
            for v in (*valores, *umbrales)
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        ]
        formas: set[str] = set()
        for v in anclados:
            formas |= renderizados(v)
        textos_ok = {str(t) for t in textos}

        # Las fechas se sacan antes de tokenizar números, o se partirían en tres.
        restante = texto
        for fecha in FECHA.findall(texto):
            if fecha not in textos_ok:
                LOGGER.warning("grounding_fecha_sin_anclaje")
            restante = restante.replace(fecha, " ")

        huerfanas: list[Huerfana] = []
        citadas = ancladas = 0
        for m in NUMERO.finditer(restante):
            token, porcentaje = m.group(1), bool(m.group(2))
            citadas += 1
            if token in TOLERADOS and not porcentaje:
                ancladas += 1
                continue
            if token in formas or token.replace(",", "") in formas:
                ancladas += 1
                continue
            if self._cotejo_numerico(token, porcentaje, anclados):
                ancladas += 1
                continue
            huerfanas.append(Huerfana(texto=token, posicion=m.start(1), es_porcentaje=porcentaje))

        pii = self._pii(texto, textos_ok, formas)
        resultado = Resultado(
            ok=not huerfanas and not pii,
            huerfanas=tuple(huerfanas),
            cifras_citadas=citadas,
            cifras_ancladas=ancladas,
            pii_detectada=tuple(pii),
        )
        if not resultado.ok:
            self.bloqueadas += 1
            LOGGER.error(
                "grounding_bloqueado motivo=%s huerfanas=%s",
                resultado.motivo,
                [h.texto for h in huerfanas],
            )
        self._historial.append(resultado)
        return resultado

    def _cotejo_numerico(self, token: str, porcentaje: bool, anclados: list[float]) -> bool:
        """Respaldo por valor, con tolerancia relativa, para formatos no previstos."""
        candidatos = _sin_separadores(token)
        if porcentaje:
            # «40%» puede venir de 0.40 o de 40. Las dos lecturas se admiten.
            candidatos |= {c / 100.0 for c in candidatos}
        for c in candidatos:
            for a in anclados:
                escala = max(abs(a), abs(c), 1.0)
                if abs(a - c) <= TOLERANCIA_RELATIVA * escala:
                    return True
        return False

    def _pii(self, texto: str, textos_ok: set[str], formas: set[str]) -> list[str]:
        """Correos y secuencias largas de dígitos que ningún tool devolvió.

        Se devuelve el **tipo**, no el valor: incluirlo lo escribiría en el log, que es
        justo lo que `docs/05_security.md` §5 evita.
        """
        hallazgos: list[str] = []
        if any(c not in textos_ok for c in CORREO.findall(texto)):
            hallazgos.append("correo_sin_respaldo")
        for d in DIGITOS_LARGOS.findall(texto):
            if d not in textos_ok and d not in formas:
                hallazgos.append("secuencia_de_digitos_sin_respaldo")
                break
        return hallazgos

    @property
    def tasa_de_bloqueo(self) -> float | None:
        """Bloqueos sobre **respuestas revisadas**. `None` si no se revisó ninguna."""
        if not self.revisadas:
            return None
        return self.bloqueadas / self.revisadas

    def metricas(self) -> dict[str, Any]:
        return {
            "respuestas_revisadas": self.revisadas,
            "respuestas_bloqueadas": self.bloqueadas,
            "tasa_de_bloqueo_sobre_revisadas": self.tasa_de_bloqueo,
            "motivos": {
                m: sum(1 for r in self._historial if r.motivo == m)
                for m in ("cifra_sin_anclaje", "pii_sin_respaldo")
                if any(r.motivo == m for r in self._historial)
            },
        }


# Checker del proceso. El arnés de evaluación lo reemplaza por uno limpio por corrida.
CHECKER = GroundingChecker()
