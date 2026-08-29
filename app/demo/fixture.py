"""Golden path de la demo (roadmap, paso 0.3): un booking de exportación que
sale bien hasta que el buque hace un transbordo no planeado. 5 pasos, con una
decisión humana en el medio. demo/provider.py reproduce estos eventos de forma
guionizada; demo/driver.py los dispara uno a uno vía POST /demo/advance.
"""

from __future__ import annotations

from typing import Any

from app.flow.models import FlowDefinition, StepDefinition

GOLDEN_PATH_WORKFLOW_ID = "logistics-booking"

GOLDEN_PATH_STEPS: list[StepDefinition] = [
    StepDefinition(
        id="booking_received",
        type="booking_received",
        title="Booking recibido",
        objective="Confirmar los datos del booking a partir del email del cliente.",
        inputs=["booking_email"],
        requires_human_review=False,
    ),
    StepDefinition(
        id="vessel_departure",
        type="vessel_departure",
        title="Salida del buque",
        objective="Registrar la salida del buque desde el puerto de origen.",
        inputs=["vessel_name", "origin_port", "departure_date"],
        requires_human_review=False,
    ),
    StepDefinition(
        id="transshipment_anomaly",
        type="transshipment_anomaly",
        title="Transbordo no planeado",
        objective="Detectar el transbordo y decidir si se busca ruta alterna.",
        inputs=["transshipment_port", "delay_days"],
        requires_human_review=True,
    ),
    StepDefinition(
        id="route_resolution",
        type="route_resolution",
        title="Resolución de ruta",
        objective="Aplicar la decisión humana y recalcular el ETA.",
        inputs=["chosen_action"],
        requires_human_review=False,
    ),
    StepDefinition(
        id="delivery_eta",
        type="delivery_eta",
        title="ETA de entrega actualizado",
        objective="Cerrar el run con el ETA final de entrega.",
        inputs=["final_eta"],
        requires_human_review=False,
    ),
]

GOLDEN_PATH_FLOW = FlowDefinition(
    workflow_id=GOLDEN_PATH_WORKFLOW_ID,
    version=1,
    steps=GOLDEN_PATH_STEPS,
)

# Eventos guionizados que demo/provider.py entrega en orden. Cada uno trae los
# `inputs` que su step declara, más el `verdict` genérico que consume
# synthesis/ (nunca strings de dominio como "vessel" o "bol" fuera de aquí).
SCRIPTED_EVENTS: list[dict[str, Any]] = [
    {
        "step_id": "booking_received",
        "data": {
            "booking_email": "Booking BK-4471 confirmado: 3 contenedores, Muebles del Sur -> Rotterdam.",
        },
        "verdict": "ok",
    },
    {
        "step_id": "vessel_departure",
        "data": {
            "vessel_name": "MSC Aurora",
            "origin_port": "Valparaíso",
            "departure_date": "2026-08-20",
        },
        "verdict": "ok",
    },
    {
        "step_id": "transshipment_anomaly",
        "data": {
            "transshipment_port": "Balboa",
            "delay_days": 9,
        },
        "verdict": "attention",
        "pending_decision": {
            "prompt": "El transbordo en Balboa agrega 9 días. ¿Buscar ruta alterna?",
            "available_actions": ["find_alternative", "accept_delay"],
        },
    },
    {
        "step_id": "route_resolution",
        "data": {
            "chosen_action": "find_alternative",
            "recovered_days": 6,
        },
        "verdict": "ok",
    },
    {
        "step_id": "delivery_eta",
        "data": {
            "final_eta": "2026-09-15",
        },
        "verdict": "ok",
    },
]
