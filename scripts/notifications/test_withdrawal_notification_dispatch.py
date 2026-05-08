from unittest.mock import patch

from galint_flask.services.inventory import inventory_service


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: esperado={expected!r} obtido={actual!r}")


def run():
    with patch("galint_flask.services.inventory.operation_log_service.notify_telegram") as notify_log, \
         patch("galint_flask.services.notification_router.NotificationRouterService.route_withdrawal") as route_withdrawal, \
         patch("galint_flask.services.notification_router.NotificationRouterService.route_permanent_custody") as route_permanent:

        inventory_service._dispatch_movement_notification(
            type("EntradaStub", (), {})(),
            is_entrada=True,
            skip_notification=False,
            operation_log_id=101,
        )
        notify_log.assert_called_once_with(101)
        route_withdrawal.assert_not_called()
        route_permanent.assert_not_called()

    with patch("galint_flask.services.inventory.operation_log_service.notify_telegram") as notify_log, \
         patch("galint_flask.services.notification_router.NotificationRouterService.route_withdrawal") as route_withdrawal, \
         patch("galint_flask.services.notification_router.NotificationRouterService.route_permanent_custody") as route_permanent:

        movimento = type("SaidaTemporariaStub", (), {"id_saida": 202, "tipo_custodia": "temporaria"})()
        inventory_service._dispatch_movement_notification(
            movimento,
            is_entrada=False,
            skip_notification=False,
            operation_log_id=2020,
        )
        route_withdrawal.assert_called_once_with(202, force_single=True)
        route_permanent.assert_not_called()
        notify_log.assert_not_called()

    with patch("galint_flask.services.inventory.operation_log_service.notify_telegram") as notify_log, \
         patch("galint_flask.services.notification_router.NotificationRouterService.route_withdrawal") as route_withdrawal, \
         patch("galint_flask.services.notification_router.NotificationRouterService.route_permanent_custody") as route_permanent:

        movimento = type("SaidaPermanenteStub", (), {"id_saida": 303, "tipo_custodia": "permanente"})()
        inventory_service._dispatch_movement_notification(
            movimento,
            is_entrada=False,
            skip_notification=False,
            operation_log_id=3030,
        )
        route_permanent.assert_called_once_with(303)
        route_withdrawal.assert_not_called()
        notify_log.assert_not_called()

    with patch("galint_flask.services.inventory.operation_log_service.notify_telegram") as notify_log, \
         patch("galint_flask.services.notification_router.NotificationRouterService.route_withdrawal") as route_withdrawal, \
         patch("galint_flask.services.notification_router.NotificationRouterService.route_permanent_custody") as route_permanent:

        movimento = type("SaidaSemNotificacaoStub", (), {"id_saida": 404, "tipo_custodia": "temporaria"})()
        inventory_service._dispatch_movement_notification(
            movimento,
            is_entrada=False,
            skip_notification=True,
            operation_log_id=4040,
        )
        route_permanent.assert_not_called()
        route_withdrawal.assert_not_called()
        notify_log.assert_not_called()

    print("OK: dispatch de notificações de retirada validado")


if __name__ == "__main__":
    run()