# TIC is Among Us v2.0

Proyecto de juego interactivo para **Raspberry Pi**, desarrollado en Python como parte del **MiniProyecto 2 de Taller de Aplicación TIC I (549253-1)** de la Universidad de Concepción.

El jugador utiliza un encoder rotatorio, un sensor MPU6050 y un sensor ultrasónico para resolver misiones. Una interfaz gráfica muestra los objetivos, las lecturas y la vida del jugador y del jefe. Un buzzer pasivo reproduce sonidos de victoria y derrota.

La partida completa se coordina mediante un host externo, con el que el cliente intercambia archivos JSON por SSH/SFTP. **El servidor de la partida no está implementado en `final.py`.**

## Integrantes

- Javier Espinoza Arcos.
- Ignacio Aguilar Contreras.
- Sebastián Tecay Hermosilla.

**Institución:** Universidad de Concepción, Facultad de Ingeniería, Departamento de Ingeniería Eléctrica.  
**Asignatura:** Taller de Aplicación TIC I, segundo semestre de 2026.  
**Profesor:** Vincenzo Caro Fuentes.  
**Grupo / jugador:** P04.

## Archivos del proyecto

| Archivo | Descripción |
| --- | --- |
| `final.py` | Cliente del juego: interfaz, sensores, minijuegos, buzzer y comunicación con el host. |
| `Taller_de_Aplicación_TIC_2_Copy_.pdf` | Informe del proyecto: circuito, diagramas, funcionamiento, interfaces y resultados reportados. |
| `README.md` | Descripción y guía de uso del proyecto. |
| `contador_eventos.txt` | Archivo generado durante el uso de la partida para conservar el contador de eventos entre ejecuciones. |

El archivo de entrada es **`final.py`**, aunque el comentario inicial del código conserva otro nombre de ejecución.

## Funcionalidades

- Pruebas locales de los dos minijuegos.
- Partida conectada al host: Lobby, rondas 1 y 2, y ronda final.
- Objetivos destacados en azul y lecturas actualizadas durante el juego.
- Barras de vida del jugador y del jefe, actualizadas a partir de mensajes del host.
- Registro de mensajes, confirmaciones, resultados y errores.
- Sabotajes `Delay`, `Disable` y `ScoreSteal`.
- Efectos sonoros al terminar un minijuego: victoria para `Win`; derrota para `Lose` o `TimeOut`.

## Hardware y conexiones

### Componentes

- Raspberry Pi con conector GPIO de 40 pines, fuente y acceso a un escritorio gráfico.
- Encoder rotatorio KY-040 con pulsador.
- MPU6050, módulo GY-521.
- Sensor ultrasónico HC-SR04.
- Buzzer pasivo KY-006.
- Protoboard, cables y resistencias para el divisor de tensión de ECHO.

### Asignación de GPIO

**La numeración utilizada por el programa es BCM; no corresponde a la posición física del conector.**

| Componente | Señal | GPIO BCM |
| --- | --- | --- |
| Encoder KY-040 | CLK | 16 |
| Encoder KY-040 | DT | 20 |
| Encoder KY-040 | SW | 21 |
| MPU6050 | SDA | 2 |
| MPU6050 | SCL | 3 |
| HC-SR04 | TRIG | 26 |
| HC-SR04 | ECHO, a través del divisor resistivo | 19 |
| Buzzer KY-006 | S, señal PWM | 6 |

El MPU6050 se consulta en el **bus I²C 1**, dirección **`0x68`**.

> La señal ECHO del HC-SR04 debe adaptarse al nivel de entrada de la Raspberry Pi mediante el divisor resistivo. No conectar ECHO directamente al GPIO. El montaje debe compartir una referencia de tierra y respetar las alimentaciones de cada módulo.

## Preparación e instalación

Estos pasos se realizan **en la Raspberry Pi**, dentro de la carpeta que contiene `final.py`. Las pruebas locales también requieren los componentes físicos; el programa no incluye un modo de simulación.

### 1. Instalar los paquetes del sistema

En Raspberry Pi OS con APT:

```bash
sudo apt update
sudo apt install python3-tk python3-venv python3-gpiozero i2c-tools
```

### 2. Habilitar I²C

Abrir la herramienta de configuración:

```bash
sudo raspi-config
```

Activar **I2C** dentro de las opciones de interfaces. Reiniciar si la herramienta lo solicita. Con el MPU6050 conectado, comprobar su detección:

```bash
i2cdetect -y 1
```

La dirección esperada por el código es `68`.

### 3. Crear el entorno de Python

El entorno utiliza los paquetes del sistema para acceder a GPIO Zero:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install paramiko smbus2
```

| Dependencia | Uso |
| --- | --- |
| `tkinter` y `tkinter.ttk` | Interfaz gráfica. |
| `gpiozero` | Encoder, pulsador, sensor ultrasónico y PWM del buzzer. |
| `smbus2` | Comunicación I²C con el MPU6050. El código contempla `smbus` como alternativa. |
| `paramiko` | Conexión SSH y transferencia SFTP. |

## Configuración del host

Para **Jugar partida**, revisar las constantes de conexión al comienzo de `final.py` y configurar los datos entregados para el laboratorio. Este es un ejemplo con valores de reemplazo:

```python
PLAYER_ID = "P04"
USERNAME = "TU_USUARIO"
PASSWORD = "TU_CONTRASEÑA"
HOST = "tic-host.local"
PORT = 22
REMOTE_INBOX = "/inbox"
REMOTE_OUTBOX = "/outbox"
```

El equipo debe poder resolver o alcanzar el host y disponer de permisos sobre las rutas SFTP acordadas.

> **Antes de publicar el código en GitHub:** retirar la contraseña real incluida en el archivo entregado. Mantener las credenciales reales fuera del repositorio público. La versión actual lee constantes de Python; no carga automáticamente un archivo `.env`.

Las constantes de temporización actuales son:

| Parámetro | Valor |
| --- | --- |
| `T_POLLING` | 0,3 segundos entre consultas de mensajes. |
| `T_ESPERA_ACK` | 20 segundos de espera de confirmación. |
| `TIEMPO_MAX` | 15 segundos por minijuego, antes de aplicar sabotajes. |

## Ejecución

Desde una terminal del escritorio de la Raspberry Pi, o dentro de una sesión gráfica por VNC:

```bash
source .venv/bin/activate
python final.py
```

La ventana ofrece tres opciones:

| Botón | Acción |
| --- | --- |
| **Probar juego 1** | Ejecuta Caja fuerte sin conectarse al host. |
| **Probar juego 2** | Ejecuta Calibrar la nave sin conectarse al host. |
| **Jugar partida** | Se conecta al host, solicita el ingreso al Lobby y procesa las etapas de la partida. |

Una sesión SSH de texto sin acceso a una pantalla gráfica no basta para mostrar la ventana de Tkinter.

## Minijuegos

### GameID 1: Caja fuerte

1. Se genera una combinación de tres números entre **−8 y 8**, excluyendo el cero.
2. Girar el encoder hasta alcanzar el objetivo indicado.
3. Presionar su eje para confirmar.
4. Repetir hasta completar los tres números.

Una confirmación incorrecta produce `Lose` y puntaje 0. Completar la combinación produce `Win` y puntaje 100. El conteo del encoder vuelve a cero después de cada acierto.

### GameID 2: Calibrar la nave

Las dos fases comparten el límite de tiempo del minijuego:

| Fase | Objetivo | Tolerancia | Permanencia |
| --- | --- | --- | --- |
| Inclinación | Ángulo aleatorio de magnitud entre 20° y 40°, positivo o negativo. | ±7° | 2 segundos |
| Distancia | Mano a una distancia aleatoria entre 10 y 30 cm. | ±3 cm | 2 segundos |

Salir de la tolerancia reinicia el tiempo de permanencia de la fase activa. Una inclinación de magnitud superior a 70° produce derrota en la primera fase; una distancia inferior a 3 cm produce derrota en la segunda.

### Resultados y sabotajes

Antes de aplicar sabotajes:

| Resultado | Puntaje |
| --- | --- |
| `Win` | 100 |
| `Lose` | 0 |
| `TimeOut` | Entre 1 y 99, según el avance. |

El host puede enviar los siguientes sabotajes, que se aplican a la siguiente asignación:

| Efecto | Comportamiento |
| --- | --- |
| `Delay` | Reduce el tiempo disponible, con un mínimo de 1 segundo. |
| `Disable` | Omite el minijuego y reporta `Lose` con puntaje 0. |
| `ScoreSteal` | Resta puntos antes del envío, conservando el resultado original y limitando el puntaje entre 0 y 100. |

Por ejemplo, una victoria con `ScoreSteal = 20` se informa como `Win` con puntaje 80.

### Ronda final

El jugador presiona el pulsador del encoder hasta completar el número de pulsaciones indicado en `ReactionPresses`. El valor inicial de respaldo es 10.

Cada ciclo genera una solicitud `Recover`. La interfaz cuenta una recuperación como confirmada cuando recibe `RecoverAccepted` con el `ReplyTo` correspondiente. Las vidas oficiales las determina el host.

Al recibir `Eliminated`, el cliente abandona la recuperación y espera el cierre global. `GameOver` finaliza la partida.

## Comunicación

La Raspberry Pi actúa como cliente SSH/SFTP. Envía mensajes a `/inbox` y consulta mensajes en `/outbox`.

| Intercambio | Solicitud del cliente | Confirmación del host |
| --- | --- | --- |
| Ingreso al Lobby | `Join` | `Accepted` |
| Preparación de etapa | `StageReady` | `StageReadyAccepted` |
| Resultado del minijuego | `Result` | `ResultAccepted` |
| Recuperación de vida | `Recover` | `RecoverAccepted` |

Las confirmaciones se relacionan con las solicitudes mediante `ReplyTo` y `EventID`. Los archivos de salida se suben primero como temporales y luego se renombran a `.json`. El contador local de eventos se conserva en `contador_eventos.txt`.

## Interfaz gráfica

| Widget | Función |
| --- | --- |
| `Label` | Jugador, etapa, instrucciones, misión, lecturas, tiempo, progreso y resultado. |
| `ttk.Progressbar` | Vida del jugador y del jefe recibida desde el host. |
| `Button` | Pruebas locales y comienzo de la partida conectada. |
| `Text` | Registro de eventos y mensajes. |

El tiempo y el avance del minijuego se muestran como texto. Las dos barras corresponden a las vidas.

Las vistas ilustrativas utilizadas para documentar la interfaz son **mockups con valores simulados**; no constituyen mediciones de sensores ni evidencia de una ejecución real.

## Pruebas documentadas

El informe del grupo reporta el funcionamiento de ambos minijuegos, las rondas, los sabotajes y la recuperación de vida. También señala que la conexión al host requirió varios reintentos y que no se identificó una causa específica.

[Ver el video de demostración citado en el informe](https://www.youtube.com/watch?v=EdffZihCuW8).

Estos resultados corresponden a las pruebas descritas en el informe. No se incluye una suite de pruebas automatizadas ni una matriz de compatibilidad de modelos de Raspberry Pi o versiones de dependencias.

## Limitaciones conocidas

- El procesamiento de `Assign` presupone que el host respeta el orden de eventos; no comprueba explícitamente que se haya recibido `StageActive`.
- En la ronda final, el contador de pulsaciones se reinicia aunque no llegue `RecoverAccepted`. Queda pendiente conservar o resolver la solicitud sin confirmar antes de iniciar un nuevo intercambio.
- La partida completa requiere el host y el protocolo del laboratorio. Los botones de prueba permiten ejecutar los minijuegos sin ese servicio, pero siguen necesitando hardware.

## Documentación técnica

- [Configuración de Raspberry Pi e interfaces](https://www.raspberrypi.com/documentation/computers/configuration.html).
- [Raspberry Pi OS y entornos virtuales de Python](https://www.raspberrypi.com/documentation/computers/os.html).
- [Instalación de GPIO Zero](https://gpiozero.readthedocs.io/en/stable/installing.html).
