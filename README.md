# homeassistant-edata
Esta integración para Home Assistant te permite seguir de un vistazo tus consumos y máximas potencias alcanzadas. Para ello, se apoya en proveedores de datos como datadis, por lo que necesitarás credenciales del mismo. 

![Captura Dashboard](https://i.imgur.com/P4TcGLH.png) 

## Instrucciones

1. Instala HACS en tu entorno de Home Assistant
2. Añade este repositorio (https://github.com/uvejota/homeassistant-edata) a los repositorios personalizados de HACS
3. Instala la integración. Por favor, considere que el estado actual de la integración es aún preliminar y puede lanzar fallos.
4. Configure la integración en su fichero de configuración de Home Assistant (e.g., `configuration.yaml`)
``` yaml
sensor:
  - platform: edata
    username: !secret my_datadis_username 
    password: !secret my_datadis_password 
    cups: !secret my_cups
```

A partir de este momento (tras reiniciar), le debería aparecer un nuevo sensor en Home Assistant llamado `sensor.edata_XXXX`, donde XXXX corresponde a los últimos cuatro caracteres de su CUPS. 

## Uso

NOTA: esta sección trata la visualización de un informe en texto plano, más adelante encontrará instrucciones para la generación de gráficas.

Los estadísticos recopilados por esta integración se almacenan, de momento, como atributos. Puede visualizarlos mediante la siguiente tarjeta, sustituyendo `_XXXX` cuando sea necesario (dos veces):
``` yaml
type: markdown
content: >
  {% for attr in states.sensor.edata_XXXX.attributes %} {%- if not
  attr=="friendly_name" and not attr=="unit_of_measurement"  and not
  attr=="icon" -%} **{{attr}}**: {{state_attr("sensor.edata_XXXX", attr)}} {{-
  '\n' -}} {%- endif %} {%- endfor -%}
title: Informe
```

La tarjeta anterior mostrará un informe sencillo con los siguientes datos:

| Parámetro | Tipo | Unidad | Significado |
| ------------- | ------------- | ------------- | ------------- |
| cups | `string` | - | Identificador de su CUPS |
| `contract_p1_kW` | `float` | `kW` | Potencia contratada en P1 en el contrato vigente |
| `contract_p2_kW` | `float` | `kW` | Potencia contratada en P2 en el contrato vigente |
| `yesterday_kWh` | `float` | `kWh` | Consumo total registrado durante el día de ayer |
| `yesterday_p1_kWh` | `float` | `kWh` | Consumo en P1 registrado durante el día de ayer |
| `yesterday_p2_kWh` | `float` | `kWh` | Consumo en P2 registrado durante el día de ayer |
| `yesterday_p3_kWh` | `float` | `kWh` | Consumo en P3 registrado durante el día de ayer |
| `month_kWh` | `float` | `kWh` | Consumo total registrado durante el mes en curso |
| `month_days` | `float` | `d` | Días computados en el mes en curso |
| `month_daily_kWh` | `float` | `kWh` | Consumo medio diario registrado durante el mes en curso |
| `month_p1_kWh` | `float` | `kWh` | Consumo en P1 registrado durante el mes en curso |
| `month_p2_kWh` | `float` | `kWh` | Consumo en P2 registrado durante el mes en curso |
| `month_p3_kWh` | `float` | `kWh` | Consumo en P3 registrado durante el mes en curso |
| `last_month_kWh` | `float` | `kWh` | Consumo total registrado durante el mes pasado |
| `last_month_days_kWh` | `float` | `d` | Días computados en el mes pasado |
| `last_month_daily_kWh` | `float` | `kWh` | Consumo diario registrado durante el mes pasado |
| `last_month_p1_kWh` | `float` | `kWh` | Consumo en P1 registrado durante el mes pasado |
| `last_month_p2_kWh` | `float` | `kWh` | Consumo en P2 registrado durante el mes pasado |
| `last_month_p3_kWh` | `float` | `kWh` | Consumo en P3 registrado durante el mes pasado |
| `max_power_kW` | `float` | `kW` | Máxima potencia registrada en los últimos 12 meses |
| `max_power_date` | `date` | `%Y-%m-%d %H:%S` | Fecha correspondiente a la máxima potencia registrada en los últimos 12 meses |
| `max_power_mean_kW` | `float` | `kW` | Media de las potencias máximas registradas en los últimos 12 meses |
| `max_power_90perc_kW` | `float` | `kW` | Percentil 90 de las potencias máximas registradas en los últimos 12 meses |

## Generación de gráficos (en pruebas, sólo válido a partir de v0.1.7)

A continuación se ofrecen una serie de tarjetas (en yaml) que permiten visualizar los datos obtenidos mediante gráficas interactivas generadas con un componente llamado apexcharts-card, que también debe instalarse manualmente o mediante HACS. Siga las instrucciones de https://github.com/RomRider/apexcharts-card y recuerde tener el repositorio a mano para personalizar las gráficas a continuación.

Algunas consideraciones:

* en las siguientes tarjetas deberá reemplazar XXXX por sus últimos cuatro dígitos del CUPS,
* por motivos de tiempo y capacidades (no tengo ni puñetera idea de frontend, vaya), he optado por no desarrollar una tarjeta específica para este componente, por lo que su configuración mediante apexcharts no es inmediata y requiere lectura. Si algún desarrollador frontend se anima, podemos alinearnos para construir algo chulo.
* de momento, sólo las siguientes gráficas están disponibles, pero se mejorarán y ampliarán en un futuro para añadir consumo por horas.

### Consumo diario

![GIF consumo diario](https://media.giphy.com/media/hnyH5DCpz9x4gzQWdi/giphy.gif) 

``` yaml
type: custom:apexcharts-card
graph_span: 30d
stacked: true
span:
  offset: '-1d'
experimental:
  brush: true
header:
  show: true
  title: Consumo diario
  show_states: false
  colorize_states: false
brush:
  selection_span: 10d
all_series_config:
  type: column
  unit: kWh
  show:
    legend_value: false
series:
  - entity: sensor.edata_XXXX
    name: Total
    type: column
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/daily', 
      scups: 'XXXX'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_kWh']];
              });
          }
      );
    show:
      in_chart: false
      in_brush: true
  - entity: sensor.edata_XXXX
    name: Punta
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/daily', 
      scups: 'XXXX'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_p1_kWh']];
              });
          }
      );
  - entity: sensor.edata_XXXX
    name: Llano
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/daily', 
      scups: 'XXXX'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_p2_kWh']];
              });
          }
      );
  - entity: sensor.edata_XXXX
    name: Valle
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/daily', 
      scups: 'XXXX'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_p3_kWh']];
              });
          }
      );
```

### Consumo mensual

![GIF consumo mensual](https://i.imgur.com/sgPQbfd.png) 

``` yaml
type: custom:apexcharts-card
graph_span: 395d
stacked: true
yaxis:
  - id: eje
    opposite: false
    max: '|+20|'
    min: ~0
    apex_config:
      forceNiceScale: true
header:
  show: true
  title: Consumo mensual
  show_states: false
  colorize_states: false
all_series_config:
  type: column
  unit: kWh
  yaxis_id: eje
  extend_to_end: false
  show:
    legend_value: false
series:
  - entity: sensor.edata_XXXX
    type: line
    name: Total
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/monthly', 
      scups: 'XXXX'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_kWh']];
              });
          }
      );
    show:
      in_chart: true
  - entity: sensor.edata_XXXX
    name: Punta
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/monthly', 
      scups: 'XXXX'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_p1_kWh']];
              });
          }
      );
  - entity: sensor.edata_XXXX
    name: Llano
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/monthly', 
      scups: 'XXXX'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_p2_kWh']];
              });
          }
      );
  - entity: sensor.edata_XXXX
    name: Valle
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/monthly', 
      scups: 'XXXX'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_p3_kWh']];
              });
          }
      );
```

### Maxímetro

![Captura maximetro](https://media.giphy.com/media/uCt6kqj7XN5K3PN4mE/giphy.gif)

``` yaml
type: custom:apexcharts-card
graph_span: 1y
span:
  offset: '-30d'
header:
  show: true
  title: Maxímetro
  show_states: false
  colorize_states: false
chart_type: scatter
series:
  - entity: sensor.edata_XXXX
    name: Potencia máxima
    type: column
    extend_to_end: false
    unit: kW
    show:
      extremas: true
      datalabels: false
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/maximeter', 
      scups: 'XXXX'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_kW']];
              });
          }
      );

```

### Detalle: ayer

![Captura ayer](https://i.imgur.com/tfYnVn3.png) 

``` yaml
type: custom:apexcharts-card
chart_type: pie
header:
  show: true
  title: Ayer
  show_states: true
  colorize_states: true
  floating: true
all_series_config:
  unit: kWh
  show:
    legend_value: true
    in_header: false
apex_config:
  chart:
    height: 250px
series:
  - entity: sensor.edata_XXXX
    attribute: yesterday_kWh
    show:
      in_chart: false
      in_header: true
    name: Total
  - entity: sensor.edata_XXXX
    attribute: yesterday_p1_kWh
    name: Punta
  - entity: sensor.edata_XXXX
    attribute: yesterday_p2_kWh
    name: Llano
  - entity: sensor.edata_XXXX
    attribute: yesterday_p3_kWh
    name: Valle
```

### Detalle: mes en curso

![Captura mes en curso](https://i.imgur.com/1MOF0jk.png) 

``` yaml
type: custom:apexcharts-card
chart_type: pie
header:
  show: true
  title: Mes en curso
  show_states: true
  colorize_states: true
  floating: true
all_series_config:
  show:
    legend_value: true
    in_header: false
  unit: kWh
apex_config:
  chart:
    height: 250px
series:
  - entity: sensor.edata_XXXX
    attribute: month_kWh
    show:
      in_chart: false
      in_header: true
    name: Total
  - entity: sensor.edata_XXXX
    attribute: month_p1_kWh
    name: Punta
  - entity: sensor.edata_XXXX
    attribute: month_p2_kWh
    name: Llano
  - entity: sensor.edata_XXXX
    attribute: month_p3_kWh
    name: Valle
  - entity: sensor.edata_XXXX
    unit: €
    attribute: month_pvpc_€
    show:
      in_chart: false
      in_header: true
    name: PVPC
```
### Detalle: mes anterior

![Captura mes pasado](https://i.imgur.com/UcXkbXB.png) 

``` yaml
type: custom:apexcharts-card
chart_type: pie
header:
  show: true
  title: Mes pasado
  show_states: true
  colorize_states: true
  floating: true
all_series_config:
  show:
    legend_value: true
    in_header: false
  unit: kWh
apex_config:
  chart:
    height: 250px
series:
  - entity: sensor.edata_XXXX
    attribute: last_month_kWh
    show:
      in_chart: false
      in_header: true
    name: Total
  - entity: sensor.edata_XXXX
    attribute: last_month_p1_kWh
    name: Punta
  - entity: sensor.edata_XXXX
    attribute: last_month_p2_kWh
    name: Llano
  - entity: sensor.edata_XXXX
    attribute: last_month_p3_kWh
    name: Valle
  - entity: sensor.edata_XXXX
    unit: €
    attribute: last_month_pvpc_€
    show:
      in_chart: false
      in_header: true
    name: PVPC
```
