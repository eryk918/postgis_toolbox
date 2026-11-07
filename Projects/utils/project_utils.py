# -*- coding: utf-8 -*-
from typing import List, Optional, Tuple

from qgis.PyQt.QtCore import QUrl, QUrlQuery
from qgis.core import QgsAbstractDatabaseProviderConnection, \
    QgsDataSourceUri, QgsApplication, QgsProjectStorage

from ...utils import make_query, connection_uri

DEFAULT_SCHEMA = 'public'


def project_storage() -> Optional[QgsProjectStorage]:
    return QgsApplication.projectStorageRegistry().projectStorageFromType(
        'postgresql')


def project_schemas(
        connection: QgsAbstractDatabaseProviderConnection) -> List[str]:
    rows = make_query(connection, '''
        SELECT n.nspname,
               EXISTS (SELECT 1 FROM pg_class c
                       WHERE c.relnamespace = n.oid
                           AND c.relname = 'qgis_projects'
                           AND c.relkind IN ('r', 'p'))
        FROM pg_namespace n
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
            AND n.nspname NOT LIKE 'pg\\_temp\\_%'
            AND n.nspname NOT LIKE 'pg\\_toast\\_temp\\_%'
        ORDER BY 2 DESC, 1;
    ''')
    return [row[0] for row in rows or []]


def project_uri(connection: QgsAbstractDatabaseProviderConnection,
                schema: str, name: str = '') -> str:
    uri = connection_uri(connection)
    url = QUrl()
    url.setScheme('postgresql')
    if uri.host():
        url.setHost(uri.host())
    if uri.port():
        url.setPort(int(uri.port()))
    if uri.username():
        url.setUserName(uri.username())
    if uri.password():
        url.setPassword(uri.password())
    query = QUrlQuery()
    if uri.service():
        query.addQueryItem('service', uri.service())
    if uri.authConfigId():
        query.addQueryItem('authcfg', uri.authConfigId())
    if uri.sslMode() != QgsDataSourceUri.SslPrefer:
        query.addQueryItem(
            'sslmode', QgsDataSourceUri.encodeSslMode(uri.sslMode()))
    query.addQueryItem('dbname', uri.database())
    query.addQueryItem('schema', schema)
    if name:
        query.addQueryItem('project', name)
    url.setQuery(query)
    return url.toString(QUrl.FullyEncoded)


def list_projects(connection: QgsAbstractDatabaseProviderConnection,
                  schema: str) -> List[Tuple[str, str]]:
    storage = project_storage()
    if storage is None:
        return []
    projects = []
    for name in storage.listProjects(project_uri(connection, schema)):
        found, metadata = storage.readProjectStorageMetadata(
            project_uri(connection, schema, name))
        modified = metadata.lastModified.toString('yyyy-MM-dd HH:mm') \
            if found and metadata.lastModified.isValid() else ''
        projects.append((name, modified))
    return projects


def delete_project(connection: QgsAbstractDatabaseProviderConnection,
                   schema: str, name: str) -> bool:
    storage = project_storage()
    if storage is None:
        return False
    return storage.removeProject(project_uri(connection, schema, name))
