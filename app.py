"""API REST para administrar materiales eléctricos y generar cotizaciones.

No requiere dependencias externas: usa SQLite y la librería estándar de Python.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DB_PATH = Path(__file__).with_name("cotizaciones.db")
INTERFAZ_PATH = Path(__file__).with_name("index.html")
UNIDADES_VALIDAS = {"unidad", "metro", "rollo", "caja", "kit"}


def conexion() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def inicializar_db() -> None:
    with conexion() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS materiales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            descripcion TEXT NOT NULL DEFAULT '',
            unidad TEXT NOT NULL,
            costo_unitario REAL NOT NULL CHECK(costo_unitario >= 0),
            existencias REAL NOT NULL DEFAULT 0 CHECK(existencias >= 0),
            creado_en TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cotizaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT NOT NULL,
            notas TEXT NOT NULL DEFAULT '',
            creado_en TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS partidas_cotizacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cotizacion_id INTEGER NOT NULL REFERENCES cotizaciones(id) ON DELETE CASCADE,
            material_id INTEGER NOT NULL REFERENCES materiales(id),
            nombre_material TEXT NOT NULL,
            unidad TEXT NOT NULL,
            cantidad REAL NOT NULL CHECK(cantidad > 0),
            precio_unitario REAL NOT NULL CHECK(precio_unitario >= 0)
        );
        """)


def material_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class APIHandler(BaseHTTPRequestHandler):
    server_version = "CotizadorElectricos/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def responder(self, data: dict | list, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def responder_html(self, contenido: str, status: int = 200) -> None:
        body = contenido.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def leer_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (ValueError, json.JSONDecodeError):
            self.responder({"error": "El cuerpo debe ser un objeto JSON válido."}, 400)
            return None

    def ruta(self) -> list[str]:
        return [p for p in urlparse(self.path).path.split("/") if p]

    @staticmethod
    def numero(valor, campo: str, minimo: float = 0) -> float:
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            raise ValueError(f"{campo} debe ser un número.")
        if numero < minimo:
            raise ValueError(f"{campo} debe ser mayor o igual a {minimo}.")
        return numero

    def do_GET(self) -> None:
        partes = self.ruta()
        if not partes:
            self.responder_html(INTERFAZ_PATH.read_text(encoding="utf-8"))
            return
        if partes == ["salud"]:
            self.responder({"estado": "ok", "servicio": "API de cotizaciones eléctricas"})
            return
        if partes == ["materiales"]:
            with conexion() as db:
                rows = db.execute("SELECT * FROM materiales ORDER BY nombre").fetchall()
            self.responder([material_dict(row) for row in rows])
            return
        if len(partes) == 2 and partes[0] == "cotizaciones":
            self.obtener_cotizacion(partes[1])
            return
        if partes == ["cotizaciones"]:
            with conexion() as db:
                rows = db.execute("SELECT * FROM cotizaciones ORDER BY id DESC").fetchall()
            self.responder([dict(row) for row in rows])
            return
        self.responder({"error": "Ruta no encontrada."}, 404)

    def do_POST(self) -> None:
        partes, data = self.ruta(), self.leer_json()
        if data is None:
            return
        if partes == ["materiales"]:
            self.crear_material(data)
        elif partes == ["cotizaciones"]:
            self.crear_cotizacion(data)
        else:
            self.responder({"error": "Ruta no encontrada."}, 404)

    def do_PUT(self) -> None:
        partes, data = self.ruta(), self.leer_json()
        if data is None:
            return
        if len(partes) == 2 and partes[0] == "materiales":
            self.actualizar_material(partes[1], data)
        elif len(partes) == 2 and partes[0] == "cotizaciones":
            self.actualizar_cotizacion(partes[1], data)
        else:
            self.responder({"error": "Ruta no encontrada."}, 404)

    def do_DELETE(self) -> None:
        partes = self.ruta()
        if len(partes) != 2 or partes[0] not in {"materiales", "cotizaciones"}:
            self.responder({"error": "Ruta no encontrada."}, 404)
            return
        if partes[0] == "cotizaciones":
            with conexion() as db:
                cur = db.execute("DELETE FROM cotizaciones WHERE id = ?", (partes[1],))
            if cur.rowcount == 0:
                self.responder({"error": "Cotización no encontrada."}, 404)
            else:
                self.responder({"mensaje": "Cotización eliminada."})
            return
        try:
            with conexion() as db:
                cur = db.execute("DELETE FROM materiales WHERE id = ?", (partes[1],))
        except sqlite3.IntegrityError:
            self.responder({"error": "No se puede eliminar un material que ya forma parte de una cotización."}, 409)
            return
        if cur.rowcount == 0:
            self.responder({"error": "Material no encontrado."}, 404)
        else:
            self.responder({"mensaje": "Material eliminado."})

    def validar_material(self, data: dict) -> tuple[str, str, str, float, float]:
        nombre = str(data.get("nombre", "")).strip()
        unidad = str(data.get("unidad", "")).lower().strip()
        if not nombre:
            raise ValueError("nombre es obligatorio.")
        if unidad not in UNIDADES_VALIDAS:
            raise ValueError(f"unidad debe ser una de: {', '.join(sorted(UNIDADES_VALIDAS))}.")
        return (nombre, str(data.get("descripcion", "")).strip(), unidad,
                self.numero(data.get("costo_unitario"), "costo_unitario"),
                self.numero(data.get("existencias", 0), "existencias"))

    def crear_material(self, data: dict) -> None:
        try:
            nombre, descripcion, unidad, costo, existencias = self.validar_material(data)
        except ValueError as exc:
            self.responder({"error": str(exc)}, 400); return
        with conexion() as db:
            cur = db.execute("INSERT INTO materiales(nombre, descripcion, unidad, costo_unitario, existencias, creado_en) VALUES (?, ?, ?, ?, ?, ?)",
                             (nombre, descripcion, unidad, costo, existencias, datetime.now(timezone.utc).isoformat()))
            row = db.execute("SELECT * FROM materiales WHERE id = ?", (cur.lastrowid,)).fetchone()
        self.responder(material_dict(row), 201)

    def actualizar_material(self, material_id: str, data: dict) -> None:
        with conexion() as db:
            anterior = db.execute("SELECT * FROM materiales WHERE id = ?", (material_id,)).fetchone()
        if not anterior:
            self.responder({"error": "Material no encontrado."}, 404); return
        combinado = {**dict(anterior), **data}
        try:
            nombre, descripcion, unidad, costo, existencias = self.validar_material(combinado)
        except ValueError as exc:
            self.responder({"error": str(exc)}, 400); return
        with conexion() as db:
            db.execute("UPDATE materiales SET nombre=?, descripcion=?, unidad=?, costo_unitario=?, existencias=? WHERE id=?",
                       (nombre, descripcion, unidad, costo, existencias, material_id))
            row = db.execute("SELECT * FROM materiales WHERE id = ?", (material_id,)).fetchone()
        self.responder(material_dict(row))

    def crear_cotizacion(self, data: dict) -> None:
        cliente = str(data.get("cliente", "")).strip()
        partidas = data.get("partidas")
        if not cliente or not isinstance(partidas, list) or not partidas:
            self.responder({"error": "cliente y una lista no vacía de partidas son obligatorios."}, 400); return
        try:
            with conexion() as db:
                cur = db.execute("INSERT INTO cotizaciones(cliente, notas, creado_en) VALUES (?, ?, ?)",
                    (cliente, str(data.get("notas", "")).strip(), datetime.now(timezone.utc).isoformat()))
                for partida in partidas:
                    material_id = int(partida.get("material_id"))
                    cantidad = self.numero(partida.get("cantidad"), "cantidad", 0.000001)
                    material = db.execute("SELECT * FROM materiales WHERE id = ?", (material_id,)).fetchone()
                    if not material:
                        raise ValueError(f"El material {material_id} no existe.")
                    precio = self.numero(partida.get("precio_unitario", material["costo_unitario"]), "precio_unitario")
                    db.execute("INSERT INTO partidas_cotizacion(cotizacion_id, material_id, nombre_material, unidad, cantidad, precio_unitario) VALUES (?, ?, ?, ?, ?, ?)",
                        (cur.lastrowid, material_id, material["nombre"], material["unidad"], cantidad, precio))
                cotizacion_id = cur.lastrowid
        except (ValueError, TypeError) as exc:
            self.responder({"error": str(exc)}, 400); return
        self.obtener_cotizacion(str(cotizacion_id), 201)

    def actualizar_cotizacion(self, cotizacion_id: str, data: dict) -> None:
        """Sustituye los datos y las partidas de una cotización existente."""
        cliente = str(data.get("cliente", "")).strip()
        partidas = data.get("partidas")
        if not cliente or not isinstance(partidas, list) or not partidas:
            self.responder({"error": "cliente y una lista no vacía de partidas son obligatorios."}, 400)
            return
        try:
            with conexion() as db:
                existe = db.execute("SELECT id FROM cotizaciones WHERE id = ?", (cotizacion_id,)).fetchone()
                if not existe:
                    self.responder({"error": "Cotización no encontrada."}, 404)
                    return
                # Primero validamos todo para que una edición inválida no altere la cotización.
                partidas_validas = []
                for partida in partidas:
                    material_id = int(partida.get("material_id"))
                    cantidad = self.numero(partida.get("cantidad"), "cantidad", 0.000001)
                    material = db.execute("SELECT * FROM materiales WHERE id = ?", (material_id,)).fetchone()
                    if not material:
                        raise ValueError(f"El material {material_id} no existe.")
                    precio = self.numero(partida.get("precio_unitario", material["costo_unitario"]), "precio_unitario")
                    partidas_validas.append((material_id, material["nombre"], material["unidad"], cantidad, precio))
                db.execute("UPDATE cotizaciones SET cliente = ?, notas = ? WHERE id = ?",
                           (cliente, str(data.get("notas", "")).strip(), cotizacion_id))
                db.execute("DELETE FROM partidas_cotizacion WHERE cotizacion_id = ?", (cotizacion_id,))
                db.executemany("INSERT INTO partidas_cotizacion(cotizacion_id, material_id, nombre_material, unidad, cantidad, precio_unitario) VALUES (?, ?, ?, ?, ?, ?)",
                               [(cotizacion_id, *partida) for partida in partidas_validas])
        except (ValueError, TypeError) as exc:
            self.responder({"error": str(exc)}, 400)
            return
        self.obtener_cotizacion(cotizacion_id)

    def obtener_cotizacion(self, cotizacion_id: str, status: int = 200) -> None:
        with conexion() as db:
            cotizacion = db.execute("SELECT * FROM cotizaciones WHERE id = ?", (cotizacion_id,)).fetchone()
            partidas = db.execute("SELECT material_id, nombre_material, unidad, cantidad, precio_unitario, cantidad * precio_unitario AS subtotal FROM partidas_cotizacion WHERE cotizacion_id = ?", (cotizacion_id,)).fetchall()
        if not cotizacion:
            self.responder({"error": "Cotización no encontrada."}, 404); return
        detalle = [dict(row) for row in partidas]
        self.responder({**dict(cotizacion), "partidas": detalle, "total": round(sum(p["subtotal"] for p in detalle), 2)}, status)


if __name__ == "__main__":
    inicializar_db()
    print("API disponible en http://localhost:8000")
    ThreadingHTTPServer(("0.0.0.0", 8000), APIHandler).serve_forever()
