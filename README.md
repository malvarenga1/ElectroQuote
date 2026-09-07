# API de cotizaciones de materiales eléctricos

API REST sin dependencias para registrar cables, accesorios y otros materiales; además genera cotizaciones con sus subtotales y total final. Los datos quedan guardados en `cotizaciones.db`.

## Ejecutar

Requiere Python 3.10 o posterior.

```powershell
python app.py
```

Quedará disponible en `http://localhost:8000`.

Al abrir esa dirección en el navegador encontrarás la interfaz para registrar materiales, elaborar cotizaciones, añadir comentarios y guardar cada cotización como PDF. Después de pulsar **Guardar cotización**, selecciona **Guardar como PDF** y, en el cuadro de impresión del navegador, elige **Guardar como PDF**.

Las cotizaciones ya guardadas se pueden modificar desde la pestaña **Historial**: pulsa **Editar**, realiza los cambios y selecciona **Guardar cambios**.

## Endpoints

| Método | Ruta | Uso |
|---|---|---|
| GET | `/salud` | Comprueba la API |
| GET, POST | `/materiales` | Lista o crea materiales |
| PUT, DELETE | `/materiales/{id}` | Edita o elimina un material |
| GET, POST | `/cotizaciones` | Lista o crea cotizaciones |
| GET, PUT, DELETE | `/cotizaciones/{id}` | Consulta, edita o elimina una cotización |

Las unidades permitidas son: `metro`, `unidad`, `rollo`, `caja` y `kit`.

### Crear materiales

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/materiales -ContentType 'application/json' -Body '{"nombre":"Cable THHN calibre 12","descripcion":"Cobre color rojo","unidad":"metro","costo_unitario":0.85,"existencias":500}'
```

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/materiales -ContentType 'application/json' -Body '{"nombre":"Tomacorriente doble","unidad":"unidad","costo_unitario":3.5,"existencias":40}'
```

### Crear una cotización

`precio_unitario` es opcional: si no se envía, se toma el costo actual del material. Se guarda el precio usado en la cotización para conservar el historial.

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/cotizaciones -ContentType 'application/json' -Body '{"cliente":"Constructora Ejemplo","notas":"Validez de 15 días","partidas":[{"material_id":1,"cantidad":120,"precio_unitario":1.10},{"material_id":2,"cantidad":8}]}'
```

La respuesta incluye cada partida, su `subtotal` y el `total`.
