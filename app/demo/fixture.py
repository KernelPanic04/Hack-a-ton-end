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
            "booking_email": "Booking BK-4471 confirmado: 3 contenedores para Muebles del Sur.",
            "booking": {
                "carrier": "Pacific Meridian Lines",
                "vessel": "MV Horizonte",
                "origin": "Cai Mep, Vietnam",
                "destination": "Manzanillo, Mexico",
                "etd": "2026-08-20",
                "eta": "2026-09-15",
                "containers": ["KPAU-100001", "KPAU-100002", "KPAU-100003"],
            },
            "route": {
                "waypoints": [
                    {"id": "cai_mep", "label": "Cai Mep", "lat": 10.53, "lon": 107.07, "kind": "origin"},
                    {"id": "manzanillo", "label": "Manzanillo", "lat": 19.05, "lon": -104.32, "kind": "destination"},
                ],
                "segments": [{"from": "cai_mep", "to": "manzanillo", "status": "planned"}],
                "emphasis": "normal",
            },
        },
        "verdict": "ok",
    },
    {
        "step_id": "vessel_departure",
        "data": {
            "vessel_name": "MV Horizonte",
            "origin_port": "Cai Mep",
            "departure_date": "2026-08-20",
            "route": {
                "waypoints": [
                    {"id": "cai_mep", "label": "Cai Mep", "lat": 10.53, "lon": 107.07, "kind": "origin"},
                    {"id": "manzanillo", "label": "Manzanillo", "lat": 19.05, "lon": -104.32, "kind": "destination"},
                ],
                "marker": {"lat": 13.1, "lon": 117.4, "label": "MV Horizonte"},
                "segments": [{"from": "cai_mep", "to": "manzanillo", "status": "active"}],
                "emphasis": "normal",
            },
        },
        "verdict": "ok",
    },
    {
        "step_id": "transshipment_anomaly",
        "data": {
            "transshipment_port": "Busan",
            "delay_days": 9,
            "route": {
                "waypoints": [
                    {"id": "cai_mep", "label": "Cai Mep", "lat": 10.53, "lon": 107.07, "kind": "origin"},
                    {"id": "busan", "label": "Busan", "lat": 35.1, "lon": 129.04, "kind": "stop"},
                    {"id": "manzanillo", "label": "Manzanillo", "lat": 19.05, "lon": -104.32, "kind": "destination"},
                ],
                "marker": {"lat": 35.1, "lon": 129.04, "label": "MV Horizonte"},
                "segments": [
                    {"from": "cai_mep", "to": "busan", "status": "active"},
                    {"from": "busan", "to": "manzanillo", "status": "diverted"},
                ],
                "emphasis": "warning",
            },
        },
        "verdict": "attention",
        "pending_decision": {
            "prompt": "El transbordo en Balboa agrega 9 días. ¿Buscar ruta alterna?",
            "available_actions": ["find_alternative", "accept_delay", "notify_client"],
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

# Resultados del mock después de una decisión humana. El runtime guarda la
# acción aceptada y el driver la entrega de vuelta al provider al ejecutar los
# dos pasos restantes; así el curso del run cambia realmente según la decisión.
DECISION_OUTCOMES: dict[str, dict[str, dict[str, Any]]] = {
    "find_alternative": {
        "route_resolution": {
            "data": {"chosen_action": "find_alternative", "recovered_days": 6},
            "verdict": "ok",
        },
        "delivery_eta": {"data": {"final_eta": "2026-09-15"}, "verdict": "ok"},
    },
    "accept_delay": {
        "route_resolution": {
            "data": {"chosen_action": "accept_delay", "recovered_days": 0},
            "verdict": "attention",
        },
        "delivery_eta": {"data": {"final_eta": "2026-09-21"}, "verdict": "ok"},
    },
    "notify_client": {
        "route_resolution": {
            "data": {"chosen_action": "notify_client", "recovered_days": 0, "client_notified": True},
            "verdict": "attention",
        },
        "delivery_eta": {"data": {"final_eta": "2026-09-24", "client_notified": True}, "verdict": "ok"},
    },
}
