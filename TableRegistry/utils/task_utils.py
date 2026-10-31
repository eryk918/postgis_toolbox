# -*- coding: utf-8 -*-
from typing import Any, Callable

from qgis.core import QgsTask, QgsAbstractDatabaseProviderConnection

from ...utils import create_connection_from_uri


class RegistryTask(QgsTask):
    def __init__(self, description: str, connection_uri: str,
                 function: Callable[[QgsAbstractDatabaseProviderConnection],
                                    Any]) -> None:
        super().__init__(description, QgsTask.Flags())
        self.connection_uri = connection_uri
        self.function = function
        self.result = None

    def run(self) -> bool:
        connection = create_connection_from_uri(self.connection_uri)
        if connection is None:
            return False
        self.result = self.function(connection)
        return True
