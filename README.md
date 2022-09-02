[![HACS Supported](https://img.shields.io/badge/HACS-Supported-green.svg)](https://github.com/custom-components/hacs)
![GitHub Activity](https://img.shields.io/github/commit-activity/y/uvejota/homeassistant-edata.svg?label=commits)
[![Stable](https://img.shields.io/github/release/uvejota/homeassistant-edata.svg)](https://github.com/uvejota/homeassistant-edata/releases/latest)

# homeassistant-edata

Esta integración para Home Assistant te permite seguir de un vistazo tus consumos y máximas potencias alcanzadas, obteniendo sus datos desde datadis, y ofreciendo técnicas para su representación gráfica en lovelace mediante el componente apexcharts-card, además de integrar los datos con la plataforma de energía (beta).

![Captura Dashboard](https://i.imgur.com/P4TcGLH.png)

## Instalación

Para instalar esta integración en Home Assistant necesitarás:
* una cuenta funcional (y validada) en la web www.datadis.es (no hay que marcar la casilla de la API al registrar, usaremos la privada que está habilitada por defecto),
* una instalación *reciente* y funcional de HA,
* tener o instalar HACS en tu entorno de HA, y
* (opcional/recomendado) tener o instalar el componente apexchart-cards (también disponible en HACS).

Una vez satisfecho lo anterior, los pasos a seguir para la instalación son:

1. Instalar HACS en tu entorno de Home Assistant (ver https://hacs.xyz/),
2. Añadir este repositorio (https://github.com/uvejota/homeassistant-edata) a los repositorios personalizados de HACS,
3. Instalar la integración mediante HACS, y
4. Configurarla mediante:
   * (versión >= `2022.01.0`) la UI de Home Assistant (buscar "edata" en `Configuración > Dispositivos y servicios > Añadir integración`).
   * (versión <= `2021.12.2`) `configuration.yaml`:
``` yaml
sensor:
  - platform: edata
    username: !secret my_datadis_username
    password: !secret my_datadis_password
    cups: !secret my_cups
    #experimental: false # opcional, puede ser true/false y permite probar funciones experimentales
    #debug: false # opcional, puede ser true/false y permite "desbloquear" mensajes de log de tipo info y superior
```
5. Esperar unos minutos, le aparecerá un nuevo sensor llamado `sensor.edata_xxxx` donde `xxxx` dependerá de los últimos cuatro caracteres de su CUPS.

**NOTA IMPORTANTE:** copie y pegue el CUPS directamente desde la web de Datadis, en mayúscula. Algunas distribuidoras adhieren algunos caracteres adicionales.

## Parámetros

Los estadísticos recopilados por esta integración se almacenan, de momento, como atributos. En esta página encontrará información sobre el significado de cada atributo, y cómo visualizarlos en texto.

### Tabla de parámetros

| Parámetro | Tipo | Unidad | Significado |
| ------------- | ------------- | ------------- | ------------- |
| cups | `string` | - | Identificador de su CUPS |
| `contract_p1_kW` | `float` | `kW` | Potencia contratada en P1 en el contrato vigente |
| `contract_p2_kW` | `float` | `kW` | Potencia contratada en P2 en el contrato vigente |
| `yesterday_kWh` | `float` | `kWh` | Consumo total registrado durante el día de ayer |
| `yesterday_p1_kWh` | `float` | `kWh` | Consumo en P1 registrado durante el día de ayer |
| `yesterday_p2_kWh` | `float` | `kWh` | Consumo en P2 registrado durante el día de ayer |
| `yesterday_p3_kWh` | `float` | `kWh` | Consumo en P3 registrado durante el día de ayer |
| `month_kWh` | `float` | `kWh` | Consumo total registrado durante el mes en curso (natural) |
| `month_days` | `float` | `d` | Días computados en el mes en curso |
| `month_daily_kWh` | `float` | `kWh` | Consumo medio diario registrado durante el mes en curso |
| `month_p1_kWh` | `float` | `kWh` | Consumo en P1 registrado durante el mes en curso |
| `month_p2_kWh` | `float` | `kWh` | Consumo en P2 registrado durante el mes en curso |
| `month_p3_kWh` | `float` | `kWh` | Consumo en P3 registrado durante el mes en curso |
| `last_month_kWh` | `float` | `kWh` | Consumo total registrado durante el mes pasado (natural) |
| `last_month_days` | `float` | `d` | Días computados en el mes pasado |
| `last_month_daily_kWh` | `float` | `kWh` | Consumo diario registrado durante el mes pasado |
| `last_month_p1_kWh` | `float` | `kWh` | Consumo en P1 registrado durante el mes pasado |
| `last_month_p2_kWh` | `float` | `kWh` | Consumo en P2 registrado durante el mes pasado |
| `last_month_p3_kWh` | `float` | `kWh` | Consumo en P3 registrado durante el mes pasado |
| `max_power_kW` | `float` | `kW` | Máxima potencia registrada en los últimos 12 meses |
| `max_power_date` | `date` | `%Y-%m-%d %H:%S` | Fecha correspondiente a la máxima potencia registrada en los últimos 12 meses |
| `max_power_mean_kW` | `float` | `kW` | Media de las potencias máximas registradas en los últimos 12 meses |
| `max_power_90perc_kW` | `float` | `kW` | Percentil 90 de las potencias máximas registradas en los últimos 12 meses |

## Estadísticas de HA (Long Term Statistics)

La versión más reciente de edata (>= `2022.01.0`) es compatible con las estadísticas de HA, lo cual habilita su uso en el panel de energía, y en algunas tarjetas nativas para Lovelace. Por defecto, las estadísticas generadas serán:

| statistic_id | Tipo | Unidad | Significado |
| ------------- | ------------- | ------------- | ------------- |
| `edata:xxxx_consumption` | `sum` | `kWh` | Consumo total |
| `edata:xxxx_p1_consumption` | `sum` | `kWh` | Consumo P1 |
| `edata:xxxx_p2_consumption` | `sum` | `kWh` | Consumo P2 |
| `edata:xxxx_p3_consumption` | `sum` | `kWh` | Consumo P3 |
| `edata:xxxx_maximeter` | `mean` | `kW` | Maxímetro |
| `edata:xxxx_p1_maximeter` | `mean` | `kW` | Maxímetro P1 |
| `edata:xxxx_p2_maximeter` | `mean` | `kW` | Maxímetro P2 |
| `edata:xxxx_cost`*  | `float` | `€` | Coste total |
| `edata:xxxx_power_cost`*  | `float` | `€` | Coste (término de potencia) |
| `edata:xxxx_energy_cost`*  | `float` | `€` | Coste (término de energía) |

\* Los campos marcados con asterisco no están habilitados por defecto, y se habilitan en Ajustes > Dispositivos y Servicios > XXXX (edata) - Configurar. Tendrá que configurar los costes asociados a cada término (según su contrato).

**NOTA:** no se da soporte, de momento, a PVPC ni al coste asociado a la excepción ibérica (tope del gas) por la dificultad en la obtención de datos masivos y al mantenimiento de la integración.

## Representación gráfica de los datos (requiere apexcharts-card)

### Informe textual

Puede visualizarlos a modo de informe mediante la siguiente tarjeta, **sustituyendo `xxxx`, en minúscula, cuando sea necesario (dos veces)**:

<details>
<summary>He leído las instrucciones en negrita y no voy a ignorarlas vilmente (hacer click para mostrar)</summary>

``` yaml
type: markdown
content: >
  {% for attr in states.sensor.edata_xxxx.attributes %} {%- if not
  attr=="friendly_name" and not attr=="unit_of_measurement"  and not
  attr=="icon" -%} **{{attr}}**: {{state_attr("sensor.edata_xxxx", attr)}} {{-
  '\n' -}} {%- endif %} {%- endfor -%}
title: Informe
```

</details>

### Definición de nuevos sensores a partir de los atributos
También puedes extraer uno de los atributos como un sensor aparte siguiendo el siguiente ejemplo (por [@thekimera](https://github.com/thekimera)):

<details>
<summary>He leído las instrucciones en negrita y no voy a ignorarlas vilmente</summary>

``` yaml
sensor:
  - platform: template
    sensors:
      last_month_consumption:
        friendly_name: "Consumo mes anterior"
        value_template: >-
           {{ state_attr('sensor.edata_xxxx', 'last_month_kWh') | float }}
        unit_of_measurement: kWh
```
</details>

A continuación se ofrecen una serie de tarjetas (en yaml) que permiten **visualizar los datos obtenidos mediante gráficas interactivas generadas con un componente llamado apexcharts-card**, que también debe instalarse manualmente o mediante HACS. Siga las instrucciones de https://github.com/RomRider/apexcharts-card y recuerde tener el repositorio a mano para personalizar las gráficas a continuación.

**NOTA: en las siguientes tarjetas deberá reemplazar TODAS `xxxx` por sus últimos cuatro caracteres de su CUPS**.

### Consumo diario

![GIF consumo diario](https://media.giphy.com/media/hnyH5DCpz9x4gzQWdi/giphy.gif)

<details>
<summary>He leído las instrucciones en negrita y no voy a ignorarlas vilmente</summary>


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
  - entity: sensor.edata_xxxx
    name: Total
    type: column
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/daily',
      scups: 'xxxx'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_kWh']];
              });
          }
      );
    show:
      in_chart: false
      in_brush: true
  - entity: sensor.edata_xxxx
    name: Punta
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/daily',
      scups: 'xxxx'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_p1_kWh']];
              });
          }
      );
  - entity: sensor.edata_xxxx
    name: Llano
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/daily',
      scups: 'xxxx'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_p2_kWh']];
              });
          }
      );
  - entity: sensor.edata_xxxx
    name: Valle
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/daily',
      scups: 'xxxx'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_p3_kWh']];
              });
          }
      );
```

</details>

### Consumo mensual

![GIF consumo mensual](https://i.imgur.com/sgPQbfd.png)

<details>
<summary>He leído las instrucciones en negrita y no voy a ignorarlas vilmente</summary>

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
  extend_to: end
  show:
    legend_value: false
series:
  - entity: sensor.edata_xxxx
    type: line
    name: Total
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/monthly',
      scups: 'xxxx'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_kWh']];
              });
          }
      );
    show:
      in_chart: true
  - entity: sensor.edata_xxxx
    name: Punta
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/monthly',
      scups: 'xxxx'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_p1_kWh']];
              });
          }
      );
  - entity: sensor.edata_xxxx
    name: Llano
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/monthly',
      scups: 'xxxx'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_p2_kWh']];
              });
          }
      );
  - entity: sensor.edata_xxxx
    name: Valle
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/consumptions/monthly',
      scups: 'xxxx'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_p3_kWh']];
              });
          }
      );
```

</details>

### Maxímetro

![Captura maximetro](https://media.giphy.com/media/uCt6kqj7XN5K3PN4mE/giphy.gif)

<details>
<summary>He leído las instrucciones en negrita y no voy a ignorarlas vilmente</summary>

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
  - entity: sensor.edata_xxxx
    name: Potencia máxima
    type: column
    extend_to: end
    unit: kW
    show:
      extremas: true
      datalabels: false
    data_generator: |
      return hass.connection.sendMessagePromise({
      type: 'edata/maximeter',
      scups: 'xxxx'}).then(
          (resp) => {
              return resp.map((data, index) => {
                return [new Date(data['datetime']).getTime(), data['value_kW']];
              });
          }
      );

```

</details>

### Detalle: ayer

![Captura ayer](https://i.imgur.com/tfYnVn3.png)

<details>
<summary>He leído las instrucciones en negrita y no voy a ignorarlas vilmente</summary>

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
  - entity: sensor.edata_xxxx
    attribute: yesterday_kWh
    show:
      in_chart: false
      in_header: true
    name: Total
  - entity: sensor.edata_xxxx
    attribute: yesterday_p1_kWh
    name: Punta
  - entity: sensor.edata_xxxx
    attribute: yesterday_p2_kWh
    name: Llano
  - entity: sensor.edata_xxxx
    attribute: yesterday_p3_kWh
    name: Valle
```

</details>

### Detalle: mes en curso

![Captura mes en curso](https://i.imgur.com/1MOF0jk.png)

NOTA: El precio PVPC ya no está disponible.

<details>
<summary>He leído las instrucciones en negrita y no voy a ignorarlas vilmente</summary>

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
  - entity: sensor.edata_xxxx
    attribute: month_kWh
    show:
      in_chart: false
      in_header: true
    name: Total
  - entity: sensor.edata_xxxx
    attribute: month_p1_kWh
    name: Punta
  - entity: sensor.edata_xxxx
    attribute: month_p2_kWh
    name: Llano
  - entity: sensor.edata_xxxx
    attribute: month_p3_kWh
    name: Valle
```
</details>

### Detalle: mes anterior

![Captura mes pasado](https://i.imgur.com/UcXkbXB.png)

NOTA: El precio PVPC ya no está disponible.

<details>
<summary>He leído las instrucciones en negrita y no voy a ignorarlas vilmente</summary>

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
  - entity: sensor.edata_xxxx
    attribute: last_month_kWh
    show:
      in_chart: false
      in_header: true
    name: Total
  - entity: sensor.edata_xxxx
    attribute: last_month_p1_kWh
    name: Punta
  - entity: sensor.edata_xxxx
    attribute: last_month_p2_kWh
    name: Llano
  - entity: sensor.edata_xxxx
    attribute: last_month_p3_kWh
    name: Valle
```

</details>

## FAQ

**¿Por qué no cargan los datos?**

Hermosa pregunta:

0. Si no ve los datos en datadis.es, no los verá aquí, trate de solucionar primero lo anterior. Si no ha leído o seguido las instrucciones, hágalo.
1. Si no se ha creado el sensor `sensor.edata_xxxx`, algo ha fallado y posiblemente sea una mala configuración del YAML, revise el log y siga las instrucciones.
2. Si el sensor se ha creado, pero sólo el atributo CUPS está relleno, es posible que Datadis no esté operativo en ese instante, deje la integración funcionando y se recuperará sola.
3. Si el sensor se ha creado, y el atributo CUPS no está relleno, ha debido introducir erróneamente (a) sus credenciales, (b) su CUPS. Copie y pegue todos los datos anteriores desde la web de Datadis.es. Insisto, copie y pegue, algunas distribuidoras ofrecen un número de CUPS con dos dígitos adicionales que no coinciden con el de Datadis.

Si nada de lo anterior funciona, cree una _issue_ en https://github.com/uvejota/homeassistant-edata/issues, indicando versión, sintomatología y aportando los logs del paciente, y trataré de ayudarle lo antes posible.

## ¿Por qué hay huecos en mis datos?

Respuesta corta: porque la API de datadis no te ha dado esos datos.

Respuesta larga: porque la API de datadis es impredecible y a veces responde datos vacíos `[]`, o códigos `50X`.

**¿Qué puedes hacer?**
> Esperar, sé que parece una mierda, pero confía en mí. La integración está preparada para consultar cada hora los datos que le faltan, es por este motivo que cuanto más datos te faltan, más tarda. Ella solita tratará de averigüar los huecos y solventarlos.

¡Pero es que los huecos me han destrozado el panel de estadísticas!
> De momento, puedes regenerar las estadísticas manualmente mediante un servicio (Herramientas para desarrolladores > Servicios > edata.recreate_statistics).