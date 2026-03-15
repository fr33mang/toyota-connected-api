"""Pydantic models for Toyota Connected Europe API responses."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# --- Common wrapper ---
class ApiStatus(BaseModel):
    messages: list[dict[str, Any]] = []


# --- Account ---
class PhoneNumber(BaseModel):
    countryCode: int | None = None
    phoneNumber: int | None = None
    phoneType: str | None = None
    phoneVerified: bool | None = None


class Address(BaseModel):
    addressType: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zipCode: str | None = None
    country: str | None = None


class Email(BaseModel):
    emailAddress: str | None = None
    emailType: str | None = None
    emailVerified: bool | None = None


class Customer(BaseModel):
    model_config = ConfigDict(extra="allow")
    guid: str | None = None
    forgerockId: str | None = None
    firstName: str | None = None
    lastName: str | None = None
    phoneNumbers: list[PhoneNumber] = []
    addresses: list[Address] = []
    emails: list[Email] = []
    uiLanguage: str | None = None
    preferredLanguage: str | None = None
    countryOfResidence: str | None = None


class AccountPayload(BaseModel):
    customer: Customer | None = None


class AccountResponse(BaseModel):
    status: ApiStatus | None = None
    payload: AccountPayload | None = None


# --- Vehicles ---
class Dcm(BaseModel):
    model_config = ConfigDict(extra="allow")
    dcmModelYear: str | None = None
    dcmDestination: str | None = None
    countryCode: str | None = None
    dcmSupplierName: str | None = None
    euiccid: str | None = None


class Vehicle(BaseModel):
    model_config = ConfigDict(extra="allow")
    vin: str | None = None
    subscriberGuid: str | None = None
    registrationNumber: str | None = None
    modelYear: str | None = None
    modelName: str | None = None
    modelDescription: str | None = None
    modelCode: str | None = None
    generation: str | None = None
    region: str | None = None
    status: str | None = None
    brand: str | None = None
    fuelType: str | None = None
    color: str | None = None
    nickName: str | None = None
    displayModelDescription: str | None = None
    image: str | None = None
    evVehicle: bool | None = None
    telemetryCapable: bool | None = None
    dcm: Dcm | None = None


class VehiclesResponse(BaseModel):
    status: ApiStatus | None = None
    payload: list[Vehicle] = []


# --- Location ---
class VehicleLocation(BaseModel):
    displayName: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    locationAcquisitionDatetime: str | None = None


class LocationPayload(BaseModel):
    vin: str | None = None
    lastTimestamp: str | None = None
    vehicleLocation: VehicleLocation | None = None


class LocationResponse(BaseModel):
    status: str | None = None
    code: int | None = None
    message: str | None = None
    errors: list[Any] = []
    payload: LocationPayload | None = None


# --- Trips ---
class TripSummary(BaseModel):
    model_config = ConfigDict(extra="allow")
    length: int | None = None  # meters
    duration: int | None = None  # seconds
    durationIdle: int | None = None
    countries: list[str] = []
    maxSpeed: float | None = None
    averageSpeed: float | None = None
    fuelConsumption: float | None = None
    startLat: float | None = None
    startLon: float | None = None
    startTs: str | None = None
    endLat: float | None = None
    endLon: float | None = None
    endTs: str | None = None


class TripScores(BaseModel):
    acceleration: int | None = None
    braking: int | None = None
    constantSpeed: int | None = None
    advice: int | None = None
    global_: int | None = Field(None, alias="global")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class Trip(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    category: int | None = None
    summary: TripSummary | None = None
    scores: TripScores | None = None
    route: list[Any] = []


class TripsPayload(BaseModel):
    from_: str | None = Field(None, alias="from")
    to: str | None = None
    trips: list[Trip] = []

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class TripsResponse(BaseModel):
    payload: TripsPayload | None = None


# --- Service history ---
class ServiceHistoryEntry(BaseModel):
    serviceDate: str | None = None
    mileage: str | None = None
    unit: str | None = None
    serviceProvider: str | None = None
    serviceHistoryId: str | None = None
    serviceCategory: str | None = None  # MNT, HSC, RPR, VDE
    customerCreatedRecord: bool | None = None


class ServiceHistoryPayload(BaseModel):
    serviceHistories: list[ServiceHistoryEntry] = []


class ServiceHistoryResponse(BaseModel):
    payload: ServiceHistoryPayload | None = None


# --- Next maintenance (OSB card) ---
class MaintenanceSlider(BaseModel):
    isAvailable: bool | None = None
    maintenanceDueDate: str | None = None


class TimeInterval(BaseModel):
    value: int | None = None
    unit: str | None = None


class MaintenanceSchedule(BaseModel):
    isAvailable: bool | None = None
    timeInterval: TimeInterval | None = None
    mileageInterval: TimeInterval | None = None


class NextMaintenanceResponse(BaseModel):
    slider: MaintenanceSlider | None = None
    maintenanceSchedule: MaintenanceSchedule | None = None


# --- Telemetry ---
class Odometer(BaseModel):
    value: int | None = None
    unit: str | None = None


class TelemetryPayload(BaseModel):
    fuelType: str | None = None
    odometer: Odometer | None = None
    fuelLevel: int | None = None  # percent
    timestamp: str | None = None


class TelemetryResponse(BaseModel):
    status: str | None = None
    code: int | None = None
    message: str | None = None
    errors: list[Any] = []
    payload: TelemetryPayload | None = None


# --- Vehicle health ---
class VehicleHealthPayload(BaseModel):
    vin: str | None = None
    warning: list[Any] = []
    quantityOfEngOilIcon: list[Any] = []
    wnglastUpdTime: str | None = None


class VehicleHealthResponse(BaseModel):
    status: str | None = None
    code: int | None = None
    errors: list[Any] = []
    payload: VehicleHealthPayload | None = None
