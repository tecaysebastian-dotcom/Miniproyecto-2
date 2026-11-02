#!/usr/bin/env python3
# =============================================================
#  MiniProyecto 2 - TIC is Among Us v2.0  (Ítems 1.1 a 1.4)
#  Taller de Aplicación TIC I - Universidad de Concepción
#  Grupo 04 (P04) - Versión con interfaz gráfica (tkinter)
#
#  GameID=1 -> Caja fuerte      (Encoder rotatorio KY-040)
#  GameID=2 -> Calibrar la nave (MPU6050 + Ultrasónico KY-050)
#  Ronda Final -> botón del encoder (SW, GPIO21)
#
#  Ejecutar en el escritorio de la Raspberry (o por VNC) con:
#      python3 tic_among_us.py
# =============================================================

import time
import math
import random
import json
import os
import re
import datetime
import tkinter as tk
from tkinter import ttk
import paramiko
from gpiozero import RotaryEncoder, Button, DistanceSensor, PWMOutputDevice

try:
    from smbus2 import SMBus
except ImportError:
    from smbus import SMBus

# ------------------ DATOS DE CONEXIÓN (los entrega el profesor) ------------------
PLAYER_ID = "P04"
USERNAME = "grupo04"
PASSWORD = "6Ycdhh2j2mmtZUCg"
HOST = "tic-host.local"
PORT = 22
REMOTE_INBOX = "/inbox"
REMOTE_OUTBOX = "/outbox"

T_POLLING = 0.3        # segundos entre cada revisión de /outbox (0.2 a 0.5)
T_ESPERA_ACK = 20      # segundos máximos esperando un ACK

# ------------------ PINES (numeración BCM) ------------------
PIN_CLK = 16      # Encoder CLK
PIN_DT = 20       # Encoder DT
PIN_SW = 21       # Encoder SW (botón)
PIN_TRIG = 26     # Ultrasónico TRIG
PIN_ECHO = 19     # Ultrasónico ECHO (¡con divisor de voltaje!)
PIN_BUZZER = 6    # Buzzer pasivo (melodías)

# ------------------ MÚSICA DEL BUZZER ------------------
# Frecuencia (Hz) de cada nota. El "2" es la misma nota, una octava más aguda.
NOTAS = {"DO": 262, "RE": 294, "MI": 330, "FA": 349, "SOL": 392, "LA": 440, "SI": 494,
         "DO2": 523, "RE2": 587, "MI2": 659}

# Cada melodía es una lista de (nota, duración en segundos)
MELODIA_VICTORIA = [("DO", 0.12), ("MI", 0.12), ("SOL", 0.12), ("DO2", 0.5)]
MELODIA_DERROTA = [("SOL", 0.3), ("FA", 0.3), ("MI", 0.3), ("RE", 0.8)]
MPU_DIRECCION = 0x68   # MPU6050 por I2C (SDA=GPIO2, SCL=GPIO3)

# ------------------ PARÁMETROS DE LOS JUEGOS ------------------
TIEMPO_MAX = 15        # segundos máximos por minijuego

# Juego 1
CANTIDAD_NUMEROS = 3   # números de la combinación

# Juego 2
T_MANTENER = 2.0       # segundos que hay que mantener cada posición
TOL_ANGULO = 7         # tolerancia del ángulo (grados)
ANGULO_VOLCAR = 70     # si se inclina más que esto -> Lose
TOL_DISTANCIA = 3      # tolerancia de la distancia (cm)
DISTANCIA_CHOQUE = 3   # si la mano queda más cerca que esto -> Lose

# ------------------ COLORES DEL TEXTO ------------------
TEXTO = "black"
ROJO = "red"
VERDE = "green"
AMARILLO = "orange"
CIAN = "blue"


# =============================================================
#  INTERFAZ GRÁFICA (tkinter)
#  La ventana es una columna de "etiquetas" (Label = texto en pantalla),
#  tres botones (Button) y un cuadro de texto (Text) para el registro.
#  .pack() coloca cada elemento debajo del anterior.
#  .config(text=...) cambia lo que muestra una etiqueta.
# =============================================================
ventana = None
ocupado = False     # True mientras se ejecuta un juego o la partida


def crear_ventana():
    global ventana, lbl_etapa, lbl_titulo, lbl_instruccion
    global lbl_grande, lbl_detalle, lbl_tiempo, lbl_avance, lbl_resultado, caja_log
    global lbl_vida, barra_vida, lbl_jefe, barra_jefe, lbl_objetivo

    # 1) La ventana principal
    ventana = tk.Tk()
    ventana.title("TIC is Among Us - " + PLAYER_ID)

    # 2) Etiquetas de texto, una debajo de otra
    lbl_etapa = tk.Label(ventana, text="Jugador " + PLAYER_ID + " | Etapa: -")
    lbl_etapa.pack()

    # Vida del jugador, sin cambiar la interfaz simple del programa.
    lbl_vida = tk.Label(ventana, text="Vida: esperando al host")
    lbl_vida.pack()
    barra_vida = ttk.Progressbar(ventana, maximum=100, length=300,
                               mode="determinate")
    barra_vida.pack(pady=(2, 6))
    lbl_jefe = tk.Label(ventana, text="Vida del jefe: esperando al host", fg=ROJO)
    lbl_jefe.pack()
    barra_jefe = ttk.Progressbar(ventana, maximum=100, length=300,
                               mode="determinate")
    barra_jefe.pack(pady=(2, 6))
    lbl_titulo = tk.Label(ventana, text="Bienvenidos", font=("Arial", 18))
    lbl_titulo.pack()
    lbl_instruccion = tk.Label(ventana, text="Elige una opción.", wraplength=650)
    lbl_instruccion.pack()
    # Objetivo separado de la lectura actual del sensor.
    lbl_objetivo = tk.Label(ventana, text="", fg="#173eae",
                            font=("Arial", 16, "bold"), wraplength=650,
                            padx=12, pady=8)
    lbl_objetivo.pack(fill="x", padx=12, pady=6)
    lbl_grande = tk.Label(ventana, text="", font=("Arial", 40))   # valor del sensor
    lbl_grande.pack()
    lbl_detalle = tk.Label(ventana, text="")
    lbl_detalle.pack()
    lbl_tiempo = tk.Label(ventana, text="")
    lbl_tiempo.pack()
    lbl_avance = tk.Label(ventana, text="")
    lbl_avance.pack()
    lbl_resultado = tk.Label(ventana, text="", font=("Arial", 18))
    lbl_resultado.pack()

    # 3) Botones: "command" es la función que se ejecuta al hacer clic
    tk.Button(ventana, text="Probar juego 1", command=pulsar_juego1).pack()
    tk.Button(ventana, text="Probar juego 2", command=pulsar_juego2).pack()
    tk.Button(ventana, text="Jugar partida", command=pulsar_partida).pack()

    # 4) Cuadro de texto donde se escribe el registro de mensajes
    caja_log = tk.Text(ventana, height=10)
    caja_log.pack()


def pausa(segundos):
    """Reemplaza a time.sleep(): espera, pero mantiene la ventana funcionando.
    ventana.update() redibuja la ventana y atiende los clics."""
    fin = time.time() + segundos
    while time.time() < fin:
        ventana.update()
        time.sleep(0.005)


def gui_log(texto):
    """Agrega una línea al registro de mensajes (y también a la consola)."""
    print(texto)
    caja_log.insert("end", time.strftime("%H:%M:%S  ") + texto + "\n")
    caja_log.see("end")     # bajar hasta la última línea


def gui_pantalla(titulo, instruccion=""):
    """Pone un título nuevo y borra lo que había en las demás etiquetas."""
    lbl_titulo.config(text=titulo)
    lbl_instruccion.config(text=instruccion)
    gui_objetivo("")
    lbl_grande.config(text="", fg=TEXTO)
    lbl_detalle.config(text="")
    lbl_tiempo.config(text="")
    lbl_avance.config(text="")
    lbl_resultado.config(text="")
    ventana.update()


def gui_grande(texto, color=TEXTO):
    lbl_grande.config(text=texto, fg=color)


def gui_objetivo(texto):
    """Misión activa: letras azules, distintas al valor del sensor."""
    lbl_objetivo.config(text=texto)


def gui_detalle(texto):
    lbl_detalle.config(text=texto)


def gui_tiempo(restante, total):
    if restante < 0:
        restante = 0
    lbl_tiempo.config(text="Tiempo restante: %.1f s" % restante)


def gui_avance(fraccion, texto):
    lbl_avance.config(text=texto)


def gui_resultado(resultado, score):
    lbl_resultado.config(text=resultado + "  -  Score " + str(score))
    ventana.update()


def gui_etapa(etapa):
    lbl_etapa.config(text="Jugador " + PLAYER_ID + " | Etapa: " + etapa)


def a_numero(valor):
    """Convierte 80, 80.0 o "80" en número. Devuelve None si no se puede."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return valor if math.isfinite(valor) else None
    if isinstance(valor, str):
        try:
            numero = float(valor)
            return numero if math.isfinite(numero) else None
        except ValueError:
            return None
    return None


def aplanar(dato, ruta=""):
    """Recorre el mensaje (incluyendo diccionarios y listas anidadas) y devuelve
    pares (ruta, número). Ejemplo: {"Boss": {"HP": 300}} -> [("boss/hp", 300)].
    Si hay datos de varios jugadores, solo se conservan los de PLAYER_ID."""
    pares = []
    if isinstance(dato, dict):
        for clave, valor in dato.items():
            clave = str(clave)
            if re.fullmatch(r"P\d+", clave):
                if clave != PLAYER_ID:
                    continue          # datos de otro jugador
                clave = ""
            nombre = clave.lower().replace("_", "").replace("-", "")
            pares = pares + aplanar(valor, ruta + nombre + "/")
    elif isinstance(dato, list):
        for elemento in dato:
            if isinstance(elemento, dict):
                dueno = elemento.get("PlayerID", elemento.get("player_id"))
                if dueno is not None and dueno != PLAYER_ID:
                    continue
            pares = pares + aplanar(elemento, ruta)
    else:
        numero = a_numero(dato)
        if numero is not None:
            pares.append((ruta.strip("/"), numero))
    return pares


def clasificar(ruta):
    """Decide si un campo es vida, postura o vida del jefe (o su máximo)."""
    partes = [p for p in ruta.split("/") if p]
    if len(partes) == 0:
        return None
    ultima = partes[-1]
    for palabra in ("delta", "change", "damage", "diff", "gain", "loss", "heal", "recover"):
        if palabra in ultima:
            return None               # son cambios, no el valor actual
    es_max = "max" in ultima
    es_jefe = "boss" in ruta or "jefe" in ruta
    if "posture" in ultima or "postura" in ultima:
        return "postura_max" if es_max else "postura"
    if any(p in ultima for p in ("life", "hp", "health", "vida")):
        if es_jefe:
            return "jefe_max" if es_max else "jefe"
        return "vida_max" if es_max else "vida"
    if ultima in ("boss", "jefe"):
        return "jefe"
    return None


def texto_numero(numero):
    if float(numero) == int(numero):
        return str(int(numero))
    return "%.1f" % numero


def actualizar_barra(barra, etiqueta, nombre, valor, maximo):
    if maximo is not None and maximo > 0:
        barra.config(maximum=maximo)
    if valor is None:
        return
    if valor < 0:
        valor = 0
    if valor > float(str(barra.cget("maximum"))):
        barra.config(maximum=valor)      # el primer valor grande fija el máximo
    barra.config(value=valor)
    etiqueta.config(text="%s: %s / %s" % (nombre, texto_numero(valor),
                                          texto_numero(float(str(barra.cget("maximum"))))))


def gui_estado(mensaje):
    """Muestra vida del jugador y jefe confirmadas por el host."""
    valores = {}
    for ruta, numero in aplanar(mensaje):
        tipo = clasificar(ruta)
        if tipo is not None and tipo not in valores:
            valores[tipo] = numero
    actualizar_barra(barra_vida, lbl_vida, "Vida",
                     valores.get("vida"), valores.get("vida_max"))
    actualizar_barra(barra_jefe, lbl_jefe, "Vida del jefe",
                     valores.get("jefe"), valores.get("jefe_max"))
    ventana.update_idletasks()


def reiniciar_vida():
    """Una partida nueva espera la vida inicial enviada por el host."""
    barra_vida.config(maximum=100, value=0)
    lbl_vida.config(text="Vida: esperando al host")
    barra_jefe.config(maximum=100, value=0)
    lbl_jefe.config(text="Vida del jefe: esperando al host")


def score_timeout(avance):
    """Convierte el avance (entre 0 y 1) en un Score entre 1 y 99."""
    score = round(avance * 100)
    if score < 1:
        score = 1
    if score > 99:
        score = 99
    return score


# =============================================================
#  GAMEID 1: CAJA FUERTE (Encoder rotatorio)
#  Gira el encoder hasta cada número y presiona el botón.
#  Win: los 3 números correctos | Lose: confirmar un número malo
# =============================================================
def texto_combinacion(combinacion, aciertos):
    """Ejemplo: '✔ +4    ▶ -6    • +2'"""
    partes = []
    for i in range(len(combinacion)):
        if i < aciertos:
            marca = "✔"
        elif i == aciertos:
            marca = "▶"
        else:
            marca = "•"
        partes.append(marca + " %+d" % combinacion[i])
    return "     ".join(partes)


def juego_caja_fuerte(tiempo_max):
    encoder = RotaryEncoder(PIN_CLK, PIN_DT, max_steps=0)
    boton = Button(PIN_SW, pull_up=True, bounce_time=0.05)

    # Crear una combinación al azar (sin ceros)
    combinacion = []
    for i in range(CANTIDAD_NUMEROS):
        numero = 0
        while numero == 0:
            numero = random.randint(-8, 8)
        combinacion.append(numero)

    gui_pantalla("GameID 1 · Caja fuerte",
                 "Gira el encoder hasta el número marcado con ▶ y presiona el eje para "
                 "confirmarlo. Si confirmas un número incorrecto, se activa la alarma.")
    gui_log("Caja fuerte: combinación " + str(combinacion))

    aciertos = 0
    resultado = "TimeOut"
    score = 0
    boton_antes = boton.is_pressed
    inicio = time.time()

    try:
        while True:
            transcurrido = time.time() - inicio

            # ¿Se acabó el tiempo?
            if transcurrido >= tiempo_max:
                objetivo = combinacion[aciertos]
                cercania = 1 - abs(encoder.steps - objetivo) / abs(objetivo)
                if cercania < 0:
                    cercania = 0
                avance = (aciertos + cercania) / CANTIDAD_NUMEROS
                resultado = "TimeOut"
                score = score_timeout(avance)
                gui_grande("¡TIEMPO!", AMARILLO)
                break

            # ¿Se acaba de presionar el botón?
            boton_ahora = boton.is_pressed
            if boton_ahora and not boton_antes:
                if encoder.steps == combinacion[aciertos]:
                    aciertos = aciertos + 1
                    encoder.steps = 0
                    if aciertos == CANTIDAD_NUMEROS:
                        gui_objetivo("MISIÓN COMPLETADA: combinación correcta")
                        gui_grande("¡ABIERTA!", VERDE)
                        resultado = "Win"
                        score = 100
                        break
                else:
                    gui_grande("¡ALARMA!", ROJO)
                    resultado = "Lose"
                    score = 0
                    break
            boton_antes = boton_ahora

            # Actualizar la pantalla
            if encoder.steps == combinacion[aciertos]:
                color = VERDE
            else:
                color = TEXTO
            gui_objetivo("MISIÓN: llegar a %+d y presionar el botón (%d de %d)"
                         % (combinacion[aciertos], aciertos + 1, CANTIDAD_NUMEROS))
            gui_grande("%+d" % encoder.steps, color)
            gui_detalle(texto_combinacion(combinacion, aciertos))
            gui_tiempo(tiempo_max - transcurrido, tiempo_max)
            gui_avance(aciertos / CANTIDAD_NUMEROS,
                       "Números abiertos: %d / %d" % (aciertos, CANTIDAD_NUMEROS))
            pausa(0.02)
    finally:
        # Cerrar los pines para poder jugar de nuevo sin reiniciar
        encoder.close()
        boton.close()

    gui_detalle(texto_combinacion(combinacion, aciertos))
    gui_avance(aciertos / CANTIDAD_NUMEROS,
               "Números abiertos: %d / %d" % (aciertos, CANTIDAD_NUMEROS))
    return resultado, score


# =============================================================
#  FUNCIONES DEL MPU6050
# =============================================================
def mpu_iniciar():
    bus = SMBus(1)
    bus.write_byte_data(MPU_DIRECCION, 0x6B, 0)   # despertar el sensor
    time.sleep(0.1)
    return bus


def mpu_leer(bus, registro):
    """Lee un valor de 16 bits con signo."""
    alto = bus.read_byte_data(MPU_DIRECCION, registro)
    bajo = bus.read_byte_data(MPU_DIRECCION, registro + 1)
    valor = (alto << 8) + bajo
    if valor >= 32768:
        valor = valor - 65536
    return valor


def mpu_inclinacion(bus):
    """Devuelve la inclinación del sensor en grados (-90 a 90)."""
    ax = mpu_leer(bus, 0x3B)
    ay = mpu_leer(bus, 0x3D)
    az = mpu_leer(bus, 0x3F)
    angulo = math.degrees(math.atan2(ax, math.sqrt(ay * ay + az * az)))
    return angulo


# =============================================================
#  GAMEID 2: CALIBRAR LA NAVE (MPU6050 + Ultrasónico)
#  Etapa 1: inclina el MPU6050 al ángulo pedido y mantenlo.
#  Etapa 2: pon la mano a la distancia pedida y mantenla.
#  Lose: inclinar demasiado (la nave se vuelca) o chocar el sensor
# =============================================================
def juego_calibrar_nave(tiempo_max):
    bus = None
    sensor = None
    resultado = "TimeOut"
    score = 0

    try:
        bus = mpu_iniciar()
        sensor = DistanceSensor(echo=PIN_ECHO, trigger=PIN_TRIG, max_distance=1)

        angulo_objetivo = random.choice([-1, 1]) * random.randint(20, 40)
        distancia_objetivo = random.randint(10, 30)

        gui_pantalla("GameID 2 · Calibrar la nave",
                     "Etapa 1: inclina el MPU6050 a %d° y mantenlo %.0f s.   "
                     "Etapa 2: pon la mano a %d cm del sensor y mantenla %.0f s.   "
                     "¡No lo inclines más de %d° ni acerques la mano a menos de %d cm!"
                     % (angulo_objetivo, T_MANTENER, distancia_objetivo, T_MANTENER,
                        ANGULO_VOLCAR, DISTANCIA_CHOQUE))
        gui_log("Calibrar nave: ángulo %d°, distancia %d cm" % (angulo_objetivo, distancia_objetivo))

        etapa = 1
        mantenido = 0.0
        inicio = time.time()
        ultimo = inicio

        while True:
            ahora = time.time()
            dt = ahora - ultimo
            ultimo = ahora
            transcurrido = ahora - inicio

            # ¿Se acabó el tiempo?
            if transcurrido >= tiempo_max:
                avance = ((etapa - 1) + mantenido / T_MANTENER) / 2
                resultado = "TimeOut"
                score = score_timeout(avance)
                gui_grande("¡TIEMPO!", AMARILLO)
                break

            gui_tiempo(tiempo_max - transcurrido, tiempo_max)

            if etapa == 1:
                angulo = mpu_inclinacion(bus)
                if abs(angulo) > ANGULO_VOLCAR:
                    gui_grande("¡VOLCADA!", ROJO)
                    resultado = "Lose"
                    score = 0
                    break
                if abs(angulo - angulo_objetivo) <= TOL_ANGULO:
                    mantenido = mantenido + dt
                    color = VERDE
                else:
                    mantenido = 0
                    color = TEXTO
                gui_objetivo("MISIÓN 1/2: inclinar a %d° (±%d°) durante %.1f s"
                             % (angulo_objetivo, TOL_ANGULO, T_MANTENER))
                gui_grande("%.0f°" % angulo, color)
                gui_detalle("Etapa 1 de 2  ·  Objetivo: %d° (±%d°)" % (angulo_objetivo, TOL_ANGULO))
                gui_avance(mantenido / T_MANTENER,
                           "Mantener: %.1f / %.1f s" % (mantenido, T_MANTENER))
                if mantenido >= T_MANTENER:
                    gui_log("Ángulo calibrado, pasa a la etapa 2.")
                    etapa = 2
                    mantenido = 0

            else:
                distancia = sensor.distance * 100   # metros -> centímetros
                if distancia < DISTANCIA_CHOQUE:
                    gui_grande("¡CHOQUE!", ROJO)
                    resultado = "Lose"
                    score = 0
                    break
                if abs(distancia - distancia_objetivo) <= TOL_DISTANCIA:
                    mantenido = mantenido + dt
                    color = VERDE
                else:
                    mantenido = 0
                    color = TEXTO
                gui_objetivo("MISIÓN 2/2: mano a %d cm (±%d cm) durante %.1f s"
                             % (distancia_objetivo, TOL_DISTANCIA, T_MANTENER))
                gui_grande("%.0f cm" % distancia, color)
                gui_detalle("Etapa 2 de 2  ·  Objetivo: %d cm (±%d cm)"
                            % (distancia_objetivo, TOL_DISTANCIA))
                gui_avance(mantenido / T_MANTENER,
                           "Mantener: %.1f / %.1f s" % (mantenido, T_MANTENER))
                if mantenido >= T_MANTENER:
                    gui_objetivo("MISIÓN COMPLETADA: nave calibrada")
                    gui_grande("¡CALIBRADA!", VERDE)
                    resultado = "Win"
                    score = 100
                    break

            pausa(0.05)
    finally:
        # Cerrar sensores para poder jugar de nuevo sin reiniciar
        if sensor is not None:
            sensor.close()
        if bus is not None:
            bus.close()

    return resultado, score


def ejecutar_minijuego(game_id, tiempo):
    """Ejecuta el minijuego indicado y devuelve (Result, Score)."""
    try:
        if game_id == 1:
            resultado, score = juego_caja_fuerte(tiempo)
        elif game_id == 2:
            resultado, score = juego_calibrar_nave(tiempo)
        else:
            gui_log("GameID desconocido: " + str(game_id))
            resultado, score = "Lose", 0
    except Exception as error:
        gui_log("Error en el minijuego: " + str(error) + " (revisa las conexiones del sensor)")
        gui_grande("ERROR", ROJO)
        gui_detalle("Revisa las conexiones del sensor")
        resultado, score = "Lose", 0
    gui_resultado(resultado, score)
    sonar_buzzer(resultado)
    return resultado, score


def tocar(melodia):
    """Toca una melodía en el buzzer pasivo.
    La nota puede ser un nombre ("DO") o directamente una frecuencia en Hz (523).
    Una frecuencia 0 es un silencio.
    frequency = qué nota suena;  value = 0.5 suena,  value = 0 silencio."""
    buzzer = PWMOutputDevice(PIN_BUZZER)
    try:
        for nota, duracion in melodia:
            frecuencia = NOTAS.get(nota, nota)
            if frecuencia == 0:
                buzzer.value = 0
            else:
                buzzer.frequency = frecuencia
                buzzer.value = 0.5
            pausa(duracion)
            buzzer.value = 0
            pausa(0.03)
    finally:
        buzzer.close()  # liberar el GPIO incluso si se interrumpe la música


def sonar_buzzer(resultado):
    """Win: melodía de victoria.  Lose o TimeOut: melodía de derrota."""
    if resultado == "Win":
        tocar(MELODIA_VICTORIA)
    else:
        tocar(MELODIA_DERROTA)


# =============================================================
#  COMUNICACIÓN CON EL HOST (SSH/SFTP con Paramiko)
# =============================================================
ssh = None
sftp = None
procesados = set()     # nombres de archivos de /outbox ya leídos
cola = []              # mensajes recibidos que aún no se procesan
contador_eventos = 0   # número del último EventID usado

# Mensajes que interrumpen lo que se esté haciendo
PRIORITARIOS = ["StageStart", "FinalStart", "Eliminated", "GameOver"]

# El contador de EventID se guarda en un archivo para que no se repita
# aunque se reinicie el programa
ARCHIVO_CONTADOR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "contador_eventos.txt")


def conectar():
    global ssh, sftp
    gui_log("Conectando a " + HOST + " como " + USERNAME + "...")
    ventana.update()
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD, timeout=10)
    sftp = ssh.open_sftp()
    gui_log("Conectado.")


def desconectar():
    global ssh, sftp
    try:
        if sftp is not None:
            sftp.close()
        if ssh is not None:
            ssh.close()
    except Exception:
        pass
    sftp = None
    ssh = None


def reconectar():
    gui_log("Se perdió la conexión, reconectando...")
    desconectar()
    while True:
        try:
            conectar()
            return
        except Exception as error:
            gui_log("No se pudo reconectar: " + str(error))
            pausa(2)


def cargar_contador():
    global contador_eventos
    if os.path.exists(ARCHIVO_CONTADOR):
        with open(ARCHIVO_CONTADOR) as archivo:
            contador_eventos = int(archivo.read().strip() or 0)


def nuevo_event_id():
    global contador_eventos
    contador_eventos = contador_eventos + 1
    with open(ARCHIVO_CONTADOR, "w") as archivo:
        archivo.write(str(contador_eventos))
    return "%s-%05d" % (PLAYER_ID, contador_eventos)


def hora_actual():
    """Fecha y hora en formato ISO 8601, por ejemplo 2026-10-08T12:30:00-03:00"""
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def enviar(accion, etapa, datos_extra=None):
    """Crea un mensaje .json, lo sube a /inbox y devuelve su EventID."""
    event_id = nuevo_event_id()
    mensaje = {
        "timestamp": hora_actual(),
        "PlayerID": PLAYER_ID,      # nombre usado en los ejemplos del profesor
        "player_id": PLAYER_ID,     # nombre usado en el PDF
        "Action": accion,
        "EventID": event_id,
    }
    if etapa is not None:
        mensaje["Stage"] = etapa
    if datos_extra is not None:
        for clave in datos_extra:
            mensaje[clave] = datos_extra[clave]

    texto = json.dumps(mensaje, indent=2)
    ruta = REMOTE_INBOX + "/" + event_id + ".json"
    # Se sube con otro nombre y luego se renombra, así el host nunca
    # lee un archivo que todavía se está transfiriendo
    ruta_temporal = ruta + ".tmp"
    enviado = False
    while not enviado:
        try:
            with sftp.open(ruta_temporal, "w") as archivo:
                archivo.write(texto)
            sftp.rename(ruta_temporal, ruta)
            enviado = True
        except Exception:
            reconectar()
    gui_log("  -> Enviado: " + accion + " (" + event_id + ")")
    return event_id


def revisar_outbox():
    """Descarga los mensajes nuevos de /outbox y los agrega a la cola."""
    try:
        archivos = sftp.listdir_attr(REMOTE_OUTBOX)
    except Exception:
        reconectar()
        return

    # Ordenar por fecha de modificación para procesarlos en orden de llegada
    archivos.sort(key=lambda a: (a.st_mtime, a.filename))

    for archivo in archivos:
        nombre = archivo.filename
        if nombre in procesados or not nombre.endswith(".json"):
            continue
        try:
            with sftp.open(REMOTE_OUTBOX + "/" + nombre, "r") as f:
                mensaje = json.loads(f.read().decode("utf-8"))
        except ValueError:
            continue   # el archivo aún se está escribiendo; se lee en la próxima revisión
        except Exception:
            reconectar()
            return

        procesados.add(nombre)   # no volver a procesar este archivo
        destinatario = mensaje.get("PlayerID", mensaje.get("player_id", PLAYER_ID))
        if destinatario != PLAYER_ID:
            continue
        # Actualizar al recibir: también funciona mientras se espera un ACK.
        gui_estado(mensaje)
        gui_log("  <- Recibido: " + str(mensaje.get("Action")))
        cola.append(mensaje)


def ignorar_mensajes_antiguos():
    """Marca como procesados los archivos que ya estaban en /outbox
    (por ejemplo, de una prueba anterior)."""
    antiguos = sftp.listdir(REMOTE_OUTBOX)
    for nombre in antiguos:
        procesados.add(nombre)
    gui_log("Mensajes antiguos ignorados en /outbox: " + str(len(antiguos)))


def esperar_mensaje():
    """Consulta /outbox hasta que haya un mensaje y lo devuelve."""
    while len(cola) == 0:
        revisar_outbox()
        if len(cola) == 0:
            pausa(T_POLLING)
    return cola.pop(0)


def hay_prioritario():
    for mensaje in cola:
        if mensaje.get("Action") in PRIORITARIOS:
            return True
    return False


def mostrar_error(mensaje):
    gui_log("[ERROR del host] " + json.dumps(mensaje, ensure_ascii=False))


def esperar_ack(accion_ack, event_id):
    """Espera el ACK cuyo ReplyTo coincida con event_id.
    Devuelve el ACK, o None si llegó un mensaje prioritario,
    un Error para ese evento, o se agotó el tiempo.
    Los demás mensajes que lleguen mientras tanto se guardan en la cola."""
    otros = []
    ack = None
    parar = False
    limite = time.time() + T_ESPERA_ACK

    while ack is None and not parar:
        revisar_outbox()
        while len(cola) > 0 and ack is None and not parar:
            mensaje = cola.pop(0)
            accion = mensaje.get("Action")
            if accion == accion_ack and mensaje.get("ReplyTo") == event_id:
                ack = mensaje
            elif accion == "Error":
                mostrar_error(mensaje)
                if mensaje.get("ReplyTo") == event_id:
                    parar = True
            else:
                otros.append(mensaje)
                if accion in PRIORITARIOS:
                    parar = True

        if ack is None and not parar:
            if time.time() > limite:
                gui_log("[Aviso] No llegó " + accion_ack + " para " + event_id)
                parar = True
            else:
                pausa(T_POLLING)

    # devolver a la cola (al principio) los mensajes que no eran el ACK
    cola[0:0] = otros
    return ack


# =============================================================
#  ETAPAS DE LA PARTIDA
# =============================================================
def preparar_etapa(etapa):
    """StageReady -> StageReadyAccepted (Figura 5)."""
    event_id = enviar("StageReady", etapa)
    ack = esperar_ack("StageReadyAccepted", event_id)
    if ack is not None:
        gui_detalle("Listo. Esperando que el host active la etapa...")


def jugar_asignacion(asignacion, sabotajes):
    """Assign -> minijuego -> Result -> ResultAccepted (Figura 6)."""
    try:
        game_id = int(asignacion.get("GameID"))
    except (TypeError, ValueError):
        game_id = asignacion.get("GameID")
    attempt = asignacion.get("Attempt")
    etapa = asignacion.get("Stage")
    gui_log(">>> Asignación: GameID = %s | Attempt = %s | Stage = %s" % (game_id, attempt, etapa))

    # Aplicar los sabotajes recibidos (Ronda 2)
    tiempo = TIEMPO_MAX
    deshabilitado = False
    robo = 0
    for sabotaje in sabotajes:
        efecto = sabotaje.get("Effect")
        valor = int(sabotaje.get("Value", 0))
        if efecto == "Delay":
            tiempo = tiempo - valor
        elif efecto == "Disable":
            deshabilitado = True
        elif efecto == "ScoreSteal":
            robo = robo + valor
    if tiempo < 1:
        tiempo = 1

    if deshabilitado:
        gui_pantalla("¡Sabotaje Disable!", "El minijuego GameID %s fue bloqueado. "
                     "Se reporta una derrota." % game_id)
        gui_log("Sabotaje Disable: el minijuego se omite.")
        resultado = "Lose"
        score = 0
        pausa(1.5)
    else:
        if tiempo < TIEMPO_MAX:
            gui_log("Sabotaje Delay: solo hay %d segundos." % tiempo)
        resultado, score = ejecutar_minijuego(game_id, tiempo)

    if robo > 0:
        score = score - robo
        if score < 0:
            score = 0
        if score > 100:
            score = 100
        gui_log("Sabotaje ScoreSteal: se restan %d puntos." % robo)

    gui_resultado(resultado, score)
    gui_log("Result = %s | Score = %s" % (resultado, score))

    # Si mientras se jugaba llegó un cambio de etapa, se abandona esta ronda
    revisar_outbox()
    if hay_prioritario():
        gui_log("Llegó un cambio de etapa durante el minijuego: el resultado no se envía.")
        return

    datos = {"GameID": game_id, "Attempt": attempt, "Result": resultado, "Score": score}
    event_id = enviar("Result", etapa, datos)
    ack = esperar_ack("ResultAccepted", event_id)
    if ack is not None:
        gui_detalle("Resultado confirmado. Esperando nueva asignación...")


def ronda_final(presiones_necesarias):
    """Cuenta pulsaciones del botón y envía Recover (Figura 8).
    Termina cuando llega un mensaje prioritario (Eliminated, GameOver...)."""
    boton = Button(PIN_SW, pull_up=True, bounce_time=0.05)
    contador = 0
    boton_antes = boton.is_pressed
    ultima_revision = 0
    ciclos = 0

    gui_pantalla("Ronda Final · ¡Sobrevivan!",
                 "Presiona el botón del encoder %d veces para recuperar vida."
                 % presiones_necesarias)
    try:
        while True:
            # 1) Contar pulsaciones (solo el momento en que se presiona)
            boton_ahora = boton.is_pressed
            if boton_ahora and not boton_antes:
                contador = contador + 1
            boton_antes = boton_ahora

            gui_objetivo("MISIÓN: completar %d pulsaciones para recuperar vida"
                         % presiones_necesarias)
            gui_grande("%d / %d" % (contador, presiones_necesarias), CIAN)
            gui_avance(contador / presiones_necesarias, "Pulsaciones")
            gui_detalle("Recuperaciones confirmadas: %d" % ciclos)

            # 2) Ciclo completo -> Recover -> RecoverAccepted
            if contador >= presiones_necesarias:
                gui_grande("¡RECUPERANDO!", VERDE)
                event_id = enviar("Recover", "Final")
                ack = esperar_ack("RecoverAccepted", event_id)
                if ack is not None:
                    ciclos = ciclos + 1
                contador = 0
                boton_antes = boton.is_pressed

            # 3) Revisar /outbox cada T_POLLING segundos
            if time.time() - ultima_revision >= T_POLLING:
                revisar_outbox()
                ultima_revision = time.time()

            # 4) Procesar mensajes recibidos
            while len(cola) > 0:
                mensaje = cola[0]
                accion = mensaje.get("Action")
                if accion in PRIORITARIOS:
                    return      # lo procesa el ciclo principal
                cola.pop(0)
                if accion == "Error":
                    mostrar_error(mensaje)

            pausa(0.01)
    finally:
        boton.close()


def jugar_partida():
    """Cliente completo: Lobby, Ronda 1, Ronda 2 y Ronda Final."""
    reiniciar_vida()
    cargar_contador()
    procesados.clear()
    cola.clear()
    gui_etapa("Lobby")
    gui_pantalla("Conectando...", "Conectándose al host " + HOST)
    try:
        conectar()
    except Exception as error:
        gui_log("No se pudo conectar: " + str(error))
        gui_pantalla("No se pudo conectar",
                     "Revisa los datos de conexión y que estés en la red del laboratorio.")
        gui_detalle(str(error))
        return

    try:
        ignorar_mensajes_antiguos()

        # ---------- LOBBY: Join -> Accepted ----------
        gui_pantalla("Lobby", "Solicitando el ingreso a la partida...")
        aceptado = False
        while not aceptado:
            event_id = enviar("Join", "Lobby")
            if esperar_ack("Accepted", event_id) is not None:
                aceptado = True
            else:
                gui_log("Reintentando el ingreso en 3 s...")
                pausa(3)
        gui_pantalla("Lobby", "¡Registrados! Esperando que el host inicie la partida...")
        gui_grande("EN ESPERA", CIAN)

        # ---------- CICLO PRINCIPAL ----------
        etapa = "Lobby"
        sabotajes = []
        eliminado = False
        presiones = 10

        while True:
            mensaje = esperar_mensaje()
            accion = mensaje.get("Action")

            if accion == "StageStart":
                etapa = mensaje.get("Stage")
                sabotajes = []
                gui_etapa(etapa)
                gui_pantalla("Preparando " + etapa, "Avisando al host que estamos listos...")
                preparar_etapa(etapa)

            elif accion == "FinalStart":
                etapa = "Final"
                presiones = int(mensaje.get("ReactionPresses", presiones))
                gui_etapa("Final")
                gui_pantalla("Preparando la Ronda Final",
                             "Pulsaciones por ciclo: %d" % presiones)
                preparar_etapa("Final")

            elif accion == "StageActive":
                gui_log("===== " + str(mensaje.get("Stage")) + " ACTIVA =====")
                if etapa == "Final" and not eliminado:
                    ronda_final(presiones)
                else:
                    gui_pantalla("Ronda " + str(mensaje.get("Stage")) + " activa",
                                 "Esperando la asignación de un minijuego...")

            elif accion == "Assign":
                jugar_asignacion(mensaje, sabotajes)
                sabotajes = []    # los sabotajes solo afectan a una asignación

            elif accion == "Sabotage":
                sabotajes.append(mensaje)
                gui_log("Sabotaje recibido: %s Value=%s" % (mensaje.get("Effect"), mensaje.get("Value")))

            elif accion == "LifeUpdate":
                pass    # Ya se actualizó al recibir el mensaje en revisar_outbox().

            elif accion == "Eliminated":
                eliminado = True
                actualizar_barra(barra_vida, lbl_vida, "Vida", 0, None)
                gui_pantalla("Eliminados", "Su vida llegó a cero. Esperando el fin de la partida...")
                gui_grande("ELIMINADOS", ROJO)

            elif accion == "GameOver":
                gui_pantalla("Fin de la partida")
                if eliminado:
                    gui_grande("DERROTA", ROJO)
                    gui_detalle("Fueron eliminados en la Ronda Final.")
                else:
                    gui_grande("¡GANARON!", VERDE)
                    gui_detalle("Sobrevivieron a la Ronda Final.")
                if "Winner" in mensaje:
                    lbl_resultado.config(text="Ganador: " + str(mensaje["Winner"]))
                gui_log("===== FIN DE LA PARTIDA =====")
                break

            elif accion == "Error":
                mostrar_error(mensaje)

            else:
                gui_log("Mensaje no reconocido: " + json.dumps(mensaje, ensure_ascii=False))
    finally:
        desconectar()


# =============================================================
#  BOTONES DE LA VENTANA
# =============================================================
def ejecutar_tarea(tarea):
    """tarea = 1 o 2 (probar un minijuego) o "partida"."""
    global ocupado
    if ocupado:
        return      # ya hay algo corriendo: se ignora el clic
    ocupado = True
    if tarea == 1 or tarea == 2:
        resultado, score = ejecutar_minijuego(tarea, TIEMPO_MAX)
        gui_log(">>> Prueba local GameID = %d | Result = %s | Score = %d"
                % (tarea, resultado, score))
    else:
        jugar_partida()
    ocupado = False


def pulsar_juego1():
    ejecutar_tarea(1)


def pulsar_juego2():
    ejecutar_tarea(2)


def pulsar_partida():
    ejecutar_tarea("partida")


# =============================================================
#  PROGRAMA PRINCIPAL
# =============================================================
if __name__ == "__main__":
    crear_ventana()
    gui_log("Jugador " + PLAYER_ID + " listo. Elige una opción.")
    ventana.mainloop()      # deja la ventana abierta esperando clics
