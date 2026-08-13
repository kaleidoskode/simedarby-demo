"""Dependency injection for the service layer.

Each service is constructed here and injected into routes with `Depends(...)`,
so routes stay free of datastore wiring and a service can be swapped in tests
by overriding a single dependency.

Services are added as each phase lands, for example:

    async def catalog(
        mongo_db1: AsyncIOMotorDatabase = Depends(get_mongo_db1)
    ) -> catalog_services.CatalogServices:
        return catalog_services.CatalogServices(mongo_db1)
"""
