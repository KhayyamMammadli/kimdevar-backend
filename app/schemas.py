from typing import Literal
from pydantic import BaseModel, Field


class DemoLogin(BaseModel):
    role: Literal["buyer", "seller", "admin"]


class Profile(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(default="", max_length=30)
    district: str = Field(default="Xətai", max_length=60)


class RequestInput(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    brand: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=80)
    part: Literal["Ekran", "Batareya", "Arxa qapaq", "Digər"]
    budget: float = Field(ge=0, le=100000)
    district: str = Field(default="Xətai", min_length=1, max_length=60)
    urgency: str = Field(default="Bu gün", max_length=40)
    quality: str = Field(default="Fərq etmir", max_length=60)
    note: str = Field(default="", max_length=1500)
    image_id: str | None = None


class RequestStatus(BaseModel):
    status: Literal["completed", "cancelled"]


class OfferInput(BaseModel):
    price: float = Field(gt=0, le=100000)
    quality: str = Field(default="Uyğun alternativ", max_length=60)
    condition: Literal["Yeni", "İşlənmiş"] = "Yeni"
    stock: Literal["Stokda var", "Sifarişlə"] = "Stokda var"
    installation: float = Field(default=0, ge=0, le=100000)
    delivery: bool = False
    warranty: int = Field(default=30, ge=0, le=3650)
    note: str = Field(default="", max_length=1500)
    validity_hours: int = Field(default=24, ge=1, le=168)


class StoreInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    district: str = Field(min_length=1, max_length=60)
    address: str = Field(min_length=3, max_length=240)
    phone: str = Field(default="", max_length=30)
    categories: list[Literal["Ekran", "Batareya", "Arxa qapaq", "Digər"]] = Field(
        min_length=1, max_length=4
    )
    hours: str = Field(default="09:00–20:00", max_length=50)


class MessageInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000, pattern=r"\S")


class ConversationInput(BaseModel):
    request_id: str
    store_id: str


class ReportInput(BaseModel):
    reason: str = Field(min_length=2, max_length=100)
    detail: str = Field(min_length=3, max_length=2000)


class AnalyzeInput(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
