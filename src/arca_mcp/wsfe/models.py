from pydantic import BaseModel


class CatalogItem(BaseModel):
    id: str
    description: str
