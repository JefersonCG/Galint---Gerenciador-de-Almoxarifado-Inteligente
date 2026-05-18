"""Cria massa de teste idempotente para o dominio condominial.

Uso:
    python scripts/seed_condominium_demo.py
    python scripts/seed_condominium_demo.py --dry-run

Cria:
- 2 blocos demo com unidades dedicadas
- 5 moradores ficticios (2 locatarios)
- 5 empresas prestadoras ficticias
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from galint_flask import create_app
from galint_flask.extensions import db
from galint_flask.models import CondominiumBuilding, CondominiumOwner, ServiceCompany
from galint_flask.services.condominium_structure import generate_unit_layout, sync_building_units


SEED_TAG = "[seed:condominio-demo]"


@dataclass(frozen=True)
class BuildingSpec:
    code: str
    name: str
    display_order: int
    floor_start: int
    floor_count: int
    units_per_floor: int
    unit_suffix_start: int = 1
    suffix_width: int = 2


@dataclass(frozen=True)
class ResidentSpec:
    full_name: str
    document_number: str
    rg: str
    phone: str
    email: str
    building_code: str
    unit_number: str
    relationship_type: str
    occupancy_status: str
    profession: str
    civil_status: str
    property_regime: str
    nationality: str
    correspondence_street: str
    correspondence_number: str
    correspondence_neighborhood: str
    correspondence_city: str
    correspondence_state: str


@dataclass(frozen=True)
class CompanySpec:
    corporate_name: str
    trade_name: str
    cnpj: str
    phone: str
    whatsapp: str
    email: str
    legal_representative_name: str
    legal_representative_cpf: str
    service_types: tuple[str, ...]
    status: str
    contract_start_offset_days: int
    contract_end_offset_days: int
    monthly_contract_value: float


BUILDING_SPECS: tuple[BuildingSpec, ...] = (
    BuildingSpec(
        code="DEMO-A",
        name="Bloco Demo A",
        display_order=991,
        floor_start=1,
        floor_count=2,
        units_per_floor=2,
    ),
    BuildingSpec(
        code="DEMO-B",
        name="Bloco Demo B",
        display_order=992,
        floor_start=3,
        floor_count=1,
        units_per_floor=1,
    ),
)


RESIDENT_SPECS: tuple[ResidentSpec, ...] = (
    ResidentSpec(
        full_name="Mariana Costa Alencar",
        document_number="90000000001",
        rg="100000001",
        phone="21990000001",
        email="mariana.alencar.demo@galint.local",
        building_code="DEMO-A",
        unit_number="101",
        relationship_type="proprietario",
        occupancy_status="proprietario_residente",
        profession="Advogada",
        civil_status="casada",
        property_regime="comunhao_parcial",
        nationality="Brasileira",
        correspondence_street="Rua Demo das Acacias",
        correspondence_number="101",
        correspondence_neighborhood="Centro",
        correspondence_city="Rio de Janeiro",
        correspondence_state="RJ",
    ),
    ResidentSpec(
        full_name="Felipe Moura Tavares",
        document_number="90000000002",
        rg="100000002",
        phone="21990000002",
        email="felipe.tavares.demo@galint.local",
        building_code="DEMO-A",
        unit_number="102",
        relationship_type="locatario",
        occupancy_status="imovel_locado",
        profession="Engenheiro civil",
        civil_status="solteiro",
        property_regime="nao_aplicavel",
        nationality="Brasileira",
        correspondence_street="Rua Demo das Acacias",
        correspondence_number="102",
        correspondence_neighborhood="Centro",
        correspondence_city="Rio de Janeiro",
        correspondence_state="RJ",
    ),
    ResidentSpec(
        full_name="Luciana Prado Ribeiro",
        document_number="90000000003",
        rg="100000003",
        phone="21990000003",
        email="luciana.ribeiro.demo@galint.local",
        building_code="DEMO-A",
        unit_number="201",
        relationship_type="proprietario",
        occupancy_status="proprietario_nao_residente",
        profession="Empresaria",
        civil_status="divorciada",
        property_regime="separacao_total",
        nationality="Brasileira",
        correspondence_street="Avenida Atlantica Demo",
        correspondence_number="2010",
        correspondence_neighborhood="Copacabana",
        correspondence_city="Rio de Janeiro",
        correspondence_state="RJ",
    ),
    ResidentSpec(
        full_name="Gustavo Henrique Farias",
        document_number="90000000004",
        rg="100000004",
        phone="21990000004",
        email="gustavo.farias.demo@galint.local",
        building_code="DEMO-A",
        unit_number="202",
        relationship_type="locatario",
        occupancy_status="imovel_locado",
        profession="Analista de sistemas",
        civil_status="casado",
        property_regime="comunhao_parcial",
        nationality="Brasileira",
        correspondence_street="Rua Demo da Portaria",
        correspondence_number="202",
        correspondence_neighborhood="Tijuca",
        correspondence_city="Rio de Janeiro",
        correspondence_state="RJ",
    ),
    ResidentSpec(
        full_name="Patricia Soares Lima",
        document_number="90000000005",
        rg="100000005",
        phone="21990000005",
        email="patricia.lima.demo@galint.local",
        building_code="DEMO-B",
        unit_number="301",
        relationship_type="proprietario",
        occupancy_status="proprietario_residente",
        profession="Medica",
        civil_status="viuva",
        property_regime="separacao_total",
        nationality="Brasileira",
        correspondence_street="Rua Demo do Jardim",
        correspondence_number="301",
        correspondence_neighborhood="Barra",
        correspondence_city="Rio de Janeiro",
        correspondence_state="RJ",
    ),
)


COMPANY_SPECS: tuple[CompanySpec, ...] = (
    CompanySpec(
        corporate_name="Demo Service Limpeza Ltda",
        trade_name="Demo Limpeza",
        cnpj="99000000000001",
        phone="2131000001",
        whatsapp="21981000001",
        email="limpeza.demo@galint.local",
        legal_representative_name="Carlos Matheus Pinto",
        legal_representative_cpf="91000000001",
        service_types=("limpeza", "jardinagem"),
        status="ativo",
        contract_start_offset_days=-120,
        contract_end_offset_days=120,
        monthly_contract_value=4200.0,
    ),
    CompanySpec(
        corporate_name="Demo Elevadores e Manutencao SPE",
        trade_name="Demo Elevadores",
        cnpj="99000000000002",
        phone="2131000002",
        whatsapp="21981000002",
        email="elevadores.demo@galint.local",
        legal_representative_name="Roberto Araujo Nunes",
        legal_representative_cpf="91000000002",
        service_types=("elevador", "seguranca"),
        status="ativo",
        contract_start_offset_days=-180,
        contract_end_offset_days=15,
        monthly_contract_value=9800.0,
    ),
    CompanySpec(
        corporate_name="Demo Pintura e Obras RJ Ltda",
        trade_name="Demo Pintura",
        cnpj="99000000000003",
        phone="2131000003",
        whatsapp="21981000003",
        email="pintura.demo@galint.local",
        legal_representative_name="Renata Campos Duarte",
        legal_representative_cpf="91000000003",
        service_types=("pintura", "obras"),
        status="ativo",
        contract_start_offset_days=-240,
        contract_end_offset_days=-7,
        monthly_contract_value=6500.0,
    ),
    CompanySpec(
        corporate_name="Demo Hidraulica Integrada Ltda",
        trade_name="Demo Hidraulica",
        cnpj="99000000000004",
        phone="2131000004",
        whatsapp="21981000004",
        email="hidraulica.demo@galint.local",
        legal_representative_name="Andressa Nogueira Maia",
        legal_representative_cpf="91000000004",
        service_types=("hidraulica",),
        status="inativo",
        contract_start_offset_days=-320,
        contract_end_offset_days=45,
        monthly_contract_value=3100.0,
    ),
    CompanySpec(
        corporate_name="Demo TI e Monitoramento Ltda",
        trade_name="Demo TI",
        cnpj="99000000000005",
        phone="2131000005",
        whatsapp="21981000005",
        email="ti.demo@galint.local",
        legal_representative_name="Thiago Paes de Barros",
        legal_representative_cpf="91000000005",
        service_types=("ti", "seguranca"),
        status="suspenso",
        contract_start_offset_days=-60,
        contract_end_offset_days=90,
        monthly_contract_value=5700.0,
    ),
)


def _compose_address(spec: ResidentSpec) -> str:
    return "\n".join(
        (
            f"{spec.correspondence_street}, {spec.correspondence_number}",
            spec.correspondence_neighborhood,
            f"{spec.correspondence_city} - {spec.correspondence_state}",
        )
    )


def _owner_registry_data(spec: ResidentSpec) -> dict[str, object]:
    return {
        "owner_profile": {
            "rg_issuer": "DETRAN/RJ",
            "civil_status": spec.civil_status,
            "property_regime": spec.property_regime,
            "nationality": spec.nationality,
            "profession": spec.profession,
        },
        "correspondence_address": {
            "street": spec.correspondence_street,
            "number": spec.correspondence_number,
            "neighborhood": spec.correspondence_neighborhood,
            "city": spec.correspondence_city,
            "state": spec.correspondence_state,
            "reference": SEED_TAG,
        },
    }


def _owner_attachment_checklist(spec: ResidentSpec) -> dict[str, bool]:
    has_purchase_docs = spec.relationship_type == "proprietario"
    return {
        "document_onus_reais": has_purchase_docs,
        "document_itbi": has_purchase_docs,
        "document_escritura": True,
        "document_owner_ids": True,
        "document_proxy": False,
    }


def _company_notes(spec: CompanySpec) -> str:
    return f"{SEED_TAG}\nCadastro ficticio para validacao faseada do modulo de prestadores."


def _resident_notes(spec: ResidentSpec) -> str:
    tipo = "Locatario" if spec.relationship_type == "locatario" else "Proprietario"
    return f"{SEED_TAG}\nCadastro ficticio de {tipo} para validacao por fases do modulo condominial."


def _ensure_building(spec: BuildingSpec) -> tuple[CondominiumBuilding, bool]:
    building = CondominiumBuilding.query.filter_by(code=spec.code).first()
    created = building is None
    if building is None:
        building = CondominiumBuilding(code=spec.code, created_by_matricula=None)
        db.session.add(building)

    building.name = spec.name
    building.display_order = spec.display_order
    building.floor_start = spec.floor_start
    building.floor_count = spec.floor_count
    building.units_per_floor = spec.units_per_floor
    building.unit_suffix_start = spec.unit_suffix_start
    building.suffix_width = spec.suffix_width
    building.numbering_mode = "floor_suffix"
    building.custom_units_text = None
    building.notes = f"{SEED_TAG} Bloco reservado para massa de teste do dominio condominial."
    building.active = True
    building.updated_by_matricula = None

    layout = generate_unit_layout(
        floor_start=spec.floor_start,
        floor_count=spec.floor_count,
        units_per_floor=spec.units_per_floor,
        unit_suffix_start=spec.unit_suffix_start,
        suffix_width=spec.suffix_width,
        custom_units_text="",
    )
    sync_building_units(building, layout, default_status="vago")
    for unit in building.units:
        if unit.active:
            unit.status = "vago"
    db.session.flush()
    return building, created


def _ensure_company(spec: CompanySpec) -> bool:
    today = date.today()
    company = ServiceCompany.query.filter_by(cnpj=spec.cnpj).first()
    created = company is None
    if company is None:
        company = ServiceCompany(cnpj=spec.cnpj, created_by_matricula=None)
        db.session.add(company)

    company.corporate_name = spec.corporate_name
    company.trade_name = spec.trade_name
    company.phone = spec.phone
    company.whatsapp = spec.whatsapp
    company.email = spec.email
    company.address = f"Avenida Prestador Demo, {spec.cnpj[-3:]} - Rio de Janeiro - RJ"
    company.legal_representative_name = spec.legal_representative_name
    company.legal_representative_cpf = spec.legal_representative_cpf
    company.contract_start_date = today + timedelta(days=spec.contract_start_offset_days)
    company.contract_end_date = today + timedelta(days=spec.contract_end_offset_days)
    company.service_types_json = list(spec.service_types)
    company.monthly_contract_value = spec.monthly_contract_value
    company.status = spec.status
    company.notes = _company_notes(spec)
    company.lgpd_authorized = True
    company.updated_by_matricula = None
    return created


def _ensure_resident(spec: ResidentSpec, units_by_key: dict[tuple[str, str], object]) -> bool:
    unit = units_by_key.get((spec.building_code, spec.unit_number))
    if unit is None:
        raise ValueError(f"Unidade demo nao encontrada: {spec.building_code}/{spec.unit_number}")

    owner = CondominiumOwner.query.filter_by(document_number=spec.document_number).first()
    created = owner is None
    if owner is None:
        owner = CondominiumOwner(document_number=spec.document_number, created_by_matricula=None)
        db.session.add(owner)

    owner.unit = unit
    owner.relationship_type = spec.relationship_type
    owner.person_type = "fisica"
    owner.full_name = spec.full_name
    owner.rg = spec.rg
    owner.cnh = None
    owner.phone = spec.phone
    owner.email = spec.email
    owner.correspondence_address = _compose_address(spec)
    owner.emergency_contact = f"Contato demo {spec.full_name.split()[0]} - 21 4000-0000"
    owner.occupancy_status = spec.occupancy_status
    owner.registry_data_json = _owner_registry_data(spec)
    owner.attachment_checklist_json = _owner_attachment_checklist(spec)
    owner.lgpd_authorized = True
    owner.status = "ativo"
    owner.notes = _resident_notes(spec)
    owner.updated_by_matricula = None
    unit.status = "ocupado"
    return created


def _build_units_index(buildings: tuple[CondominiumBuilding, ...]) -> dict[tuple[str, str], object]:
    units_by_key: dict[tuple[str, str], object] = {}
    for building in buildings:
        for unit in building.units:
            if unit.active:
                units_by_key[(building.code, str(unit.number))] = unit
    return units_by_key


def _print_summary(*, dry_run: bool, created_buildings: int, created_companies: int, created_residents: int) -> None:
    locatarios = sum(1 for spec in RESIDENT_SPECS if spec.relationship_type == "locatario")
    print("DRY RUN concluido." if dry_run else "Seed concluido com sucesso.")
    print(f"Blocos demo: {len(BUILDING_SPECS)} (novos: {created_buildings})")
    print(f"Empresas demo: {len(COMPANY_SPECS)} (novas: {created_companies})")
    print(f"Moradores demo: {len(RESIDENT_SPECS)} (novos: {created_residents}, locatarios: {locatarios})")
    print("Rotas para validacao manual:")
    print("- /administracao/condominio/cadastros")
    print("- /administracao/condominio/prestadores")
    print(f"Marcador de rastreio: {SEED_TAG}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cria massa de teste demo para condominio e prestadores")
    parser.add_argument("--dry-run", action="store_true", help="Executa validacao e desfaz tudo ao final")
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        created_buildings = 0
        buildings: list[CondominiumBuilding] = []
        for spec in BUILDING_SPECS:
            building, created = _ensure_building(spec)
            buildings.append(building)
            created_buildings += int(created)

        units_by_key = _build_units_index(tuple(buildings))

        created_companies = 0
        for spec in COMPANY_SPECS:
            created_companies += int(_ensure_company(spec))

        created_residents = 0
        for spec in RESIDENT_SPECS:
            created_residents += int(_ensure_resident(spec, units_by_key))

        if args.dry_run:
            db.session.rollback()
        else:
            db.session.commit()

        _print_summary(
            dry_run=args.dry_run,
            created_buildings=created_buildings,
            created_companies=created_companies,
            created_residents=created_residents,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())