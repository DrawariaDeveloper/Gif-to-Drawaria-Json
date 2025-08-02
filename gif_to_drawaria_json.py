import json
import os
import math
import threading
from PIL import Image, ImageSequence
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext

# --- Funciones de procesamiento de imagen ---

def rgb_to_hex(rgb_color):
    """Convierte una tupla RGB a una cadena hexadecimal."""
    return '#{:02x}{:02x}{:02x}'.format(*rgb_color).upper()

def get_drawing_commands_from_image(image_input, output_size=(100, 100), brush_thickness=2, quality_factor=1, transparency_threshold=10):
    """
    Convierte una imagen (frame de GIF) en una lista de comandos de dibujo optimizados.

    Args:
        image_input (PIL.Image.Image): Objeto PIL Image.
        output_size (tuple): Tamaño (ancho, alto) de la imagen escalada para el lienzo de Drawaria (ej. 100x100 unidades).
        brush_thickness (int): Grosor del pincel para los comandos de dibujo.
        quality_factor (int): Factor de muestreo para la optimización (1 = mejor calidad, más comandos; >1 = menor calidad, menos comandos).
        transparency_threshold (int): Umbral de canal alfa (0-255). Los píxeles con alfa <= a este valor se consideran transparentes.

    Returns:
        list: Una lista de diccionarios, donde cada diccionario es un comando de dibujo.
    """
    img = image_input.convert("RGBA")

    # Escalar la imagen al tamaño de salida deseado, manteniendo la relación de aspecto
    img.thumbnail(output_size, Image.Resampling.LANCZOS)
    
    # Crear un nuevo lienzo con el output_size y centrar la imagen
    new_img = Image.new("RGBA", output_size, (255, 255, 255, 0)) # Fondo transparente
    offset_x = (output_size[0] - img.width) // 2
    offset_y = (output_size[1] - img.height) // 2
    new_img.paste(img, (offset_x, offset_y))
    img = new_img # Usar la imagen escalada y centrada

    width, height = img.size
    pixels = img.load() # Cargar píxeles para acceso rápido

    commands = []

    for y in range(0, height, quality_factor):
        current_line_start_x = -1
        current_line_color = None

        for x in range(0, width, quality_factor):
            r, g, b, a = pixels[x, y]

            if a > transparency_threshold:  # Ignorar píxeles transparentes o casi
                hex_color = rgb_to_hex((r, g, b))

                if current_line_start_x == -1:
                    # Iniciar un nuevo segmento de línea
                    current_line_start_x = x
                    current_line_color = hex_color
                elif hex_color != current_line_color:
                    # El color cambió, finalizar el segmento anterior y empezar uno nuevo
                    commands.append({
                        "start_norm": [(current_line_start_x + offset_x) / output_size[0], (y + offset_y) / output_size[1]],
                        "end_norm": [(x - 1 + offset_x) / output_size[0], (y + offset_y) / output_size[1]], # End at pixel before color change
                        "color": current_line_color,
                        "thickness": brush_thickness
                    })
                    current_line_start_x = x
                    current_line_color = hex_color
            else:
                # Píxel transparente, finalizar el segmento actual si hay uno
                if current_line_start_x != -1:
                    commands.append({
                        "start_norm": [(current_line_start_x + offset_x) / output_size[0], (y + offset_y) / output_size[1]],
                        "end_norm": [(x - 1 + offset_x) / output_size[0], (y + offset_y) / output_size[1]],
                        "color": current_line_color,
                        "thickness": brush_thickness
                    })
                    current_line_start_x = -1
                    current_line_color = None

        # Al final de cada fila, si hay un segmento de línea activo, añadirlo
        if current_line_start_x != -1:
            commands.append({
                "start_norm": [(current_line_start_x + offset_x) / output_size[0], (y + offset_y) / output_size[1]],
                "end_norm": [(width - 1 + offset_x) / output_size[0], (y + offset_y) / output_size[1]],
                "color": current_line_color,
                "thickness": brush_thickness
            })

    return commands

def gif_to_drawaria_json_processor(gif_local_path, output_filename="drawaria_animation.json", output_size=(100, 100), brush_thickness=2, quality_factor=1, transparency_threshold=10, max_frames=None, log_callback=None):
    """
    Convierte un GIF animado local en un archivo JSON con comandos de dibujo optimizados para Drawaria.online.

    Args:
        gif_local_path (str): Ruta local del archivo GIF.
        output_filename (str): Nombre del archivo JSON de salida.
        output_size (tuple): Tamaño (ancho, alto) de cada frame en unidades de Drawaria (0-100).
        brush_thickness (int): Grosor del pincel para los comandos de dibujo.
        quality_factor (int): Factor de calidad/optimización (1 = mejor calidad, más comandos).
        transparency_threshold (int): Umbral de canal alfa (0-255) para considerar un píxel transparente.
        max_frames (int, optional): Número máximo de frames a procesar. Si es None, procesa todos.
        log_callback (callable, optional): Función para enviar mensajes de log a la GUI.
    """
    frames_data = []
    original_fps = 10 # Valor por defecto, se intenta obtener del GIF

    def log(message, tag='info'):
        if log_callback:
            log_callback(message, tag)
        else:
            print(message)

    try:
        log(f"Cargando GIF desde {gif_local_path}...")
        gif = Image.open(gif_local_path)
    except Exception as e:
        log(f"Error al cargar el GIF '{gif_local_path}': {e}", 'error')
        return

    try:
        original_fps = 1000 / gif.info['duration'] if 'duration' in gif.info else 10
        log(f"FPS original del GIF: {original_fps:.2f}")
    except:
        log("No se pudo determinar el FPS original del GIF, usando 10 FPS por defecto.")

    frame_count = 0
    total_commands = 0

    for i, frame in enumerate(ImageSequence.Iterator(gif)):
        if max_frames is not None and i >= max_frames:
            log(f"Límite de frames ({max_frames}) alcanzado. Deteniendo procesamiento.")
            break

        log(f"Procesando frame {i+1}...")
        
        commands = get_drawing_commands_from_image(
            frame, # Pasamos el objeto frame directamente
            output_size=output_size,
            brush_thickness=brush_thickness,
            quality_factor=quality_factor,
            transparency_threshold=transparency_threshold
        )
        frames_data.append(commands)
        total_commands += len(commands)
        frame_count += 1
        log(f"  - Comandos generados para frame {i+1}: {len(commands)}")

    output_data = {
        "frames": frames_data,
        "metadata": {
            "width": output_size[0],
            "height": output_size[1],
            "original_fps": original_fps,
            "frame_count": frame_count,
            "total_commands_generated": total_commands,
            "processing_options": {
                "brush_thickness": brush_thickness,
                "quality_factor": quality_factor,
                "transparency_threshold": transparency_threshold,
                "max_frames_processed": max_frames
            }
        }
    }

    try:
        with open(output_filename, 'w') as f:
            json.dump(output_data, f, indent=2)
        log(f"\n¡Proceso completado! Archivo '{output_filename}' creado con {frame_count} frames y {total_commands} comandos totales.", 'success')
    except Exception as e:
        log(f"Error al guardar el archivo JSON: {e}", 'error')


# --- Interfaz Gráfica (GUI) ---

class GIFConverterApp:
    def __init__(self, master):
        self.master = master
        master.title("GIF to Drawaria JSON Converter")
        master.geometry("450x700") 
        master.resizable(False, False)

        # Configuración de estilos
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background='#e0e0e0')
        style.configure('TLabel', background='#e0e0e0', font=('Arial', 10))
        style.configure('TButton', font=('Arial', 10, 'bold'))
        style.configure('TEntry', font=('Arial', 10))
        style.configure('TCheckbutton', background='#e0e0e0')
        style.configure('Horizontal.TScale', background='#e0e0e0')

        self.create_widgets()

    def create_widgets(self):
        # Frame principal
        main_frame = ttk.Frame(self.master, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Título
        title_label = ttk.Label(main_frame, text="GIF to Drawaria JSON Converter", font=('Arial', 14, 'bold'))
        title_label.pack(pady=10)

        # Entrada de GIF (solo local)
        gif_frame = ttk.LabelFrame(main_frame, text="Seleccionar Archivo GIF", padding="10")
        gif_frame.pack(fill=tk.X, pady=5)

        self.gif_path_var = tk.StringVar(value="")
        gif_entry = ttk.Entry(gif_frame, textvariable=self.gif_path_var, width=40, state='readonly') # Solo lectura
        gif_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        browse_button = ttk.Button(gif_frame, text="Examinar...", command=self.browse_gif)
        browse_button.pack(side=tk.RIGHT)

        # Opciones de procesamiento
        options_frame = ttk.LabelFrame(main_frame, text="Opciones de Conversión", padding="10")
        options_frame.pack(fill=tk.X, pady=5)

        # Función auxiliar para crear sliders
        def create_slider(parent, label_text, var_name, from_, to, default, resolution=1, unit=""):
            frame = ttk.Frame(parent)
            frame.pack(fill=tk.X, pady=2)
            
            label = ttk.Label(frame, text=label_text)
            label.pack(side=tk.LEFT, padx=(0,5))

            var = tk.DoubleVar(value=default) 
            setattr(self, var_name, var)

            # Define display_var BEFORE the lambda function
            display_var = tk.StringVar(value=f"{default:.0f}{unit}" if resolution == 1 else f"{default:.1f}{unit}")
            
            # FIX 1: Capture display_var in the lambda's default argument
            slider = ttk.Scale(frame, from_=from_, to=to, orient=tk.HORIZONTAL, variable=var, 
                               command=lambda s, display_var=display_var: display_var.set(f"{float(s):.0f}{unit}" if resolution == 1 else f"{float(s):.1f}{unit}"))
            slider.set(default)
            slider.pack(side=tk.LEFT, fill=tk.X, expand=True)

            display_label = ttk.Label(frame, textvariable=display_var, width=5)
            display_label.pack(side=tk.LEFT, padx=(5,0))


        create_slider(options_frame, "Ancho de Salida (px):", "output_width_var", 10, 200, 30)
        create_slider(options_frame, "Alto de Salida (px):", "output_height_var", 10, 200, 30)
        create_slider(options_frame, "Grosor del Pincel:", "brush_thickness_var", 1, 10, 2)
        create_slider(options_frame, "Factor de Calidad (1-10):", "quality_factor_var", 1, 10, 1) # Menor valor = más detalle
        create_slider(options_frame, "Umbral Transparencia (0-255):", "transparency_threshold_var", 0, 255, 10)
        
        # Max Frames
        max_frames_frame = ttk.Frame(options_frame)
        max_frames_frame.pack(fill=tk.X, pady=2)
        ttk.Label(max_frames_frame, text="Máx. Frames (0=Todos):").pack(side=tk.LEFT, padx=(0,5))
        self.max_frames_var = tk.IntVar(value=0)
        ttk.Entry(max_frames_frame, textvariable=self.max_frames_var, width=7).pack(side=tk.LEFT)

        # Botón de conversión
        self.convert_button = ttk.Button(main_frame, text="Convertir GIF a Drawaria JSON", command=self.start_conversion_thread)
        self.convert_button.pack(pady=10)

        # Área de Log
        self.log_text = scrolledtext.ScrolledText(main_frame, width=50, height=15, state='disabled', wrap=tk.WORD, font=('Consolas', 9))
        self.log_text.pack(pady=5, fill=tk.BOTH, expand=True)
        self.log_text.tag_config('info', foreground='blue')
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('error', foreground='red')

    def log_message(self, message, tag='info'):
        # Ejecutar en el hilo principal de Tkinter
        self.master.after(0, self._append_log, message, tag)

    def _append_log(self, message, tag):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + '\n', tag)
        self.log_text.yview(tk.END) # Auto-scroll
        self.log_text.config(state='disabled')

    def browse_gif(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("GIF files", "*.gif"), ("All files", "*.*")]
        )
        if file_path:
            self.gif_path_var.set(file_path)

    def start_conversion_thread(self):
        # Deshabilitar el botón para evitar múltiples clics
        self.convert_button.config(state=tk.DISABLED)
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END) # Limpiar log
        self.log_text.config(state='disabled')
        self.log_message("Iniciando conversión...", 'info')

        # Obtener valores de la GUI
        gif_local_path = self.gif_path_var.get()
        output_width = int(self.output_width_var.get())
        output_height = int(self.output_height_var.get())
        brush_thickness = int(self.brush_thickness_var.get())
        quality_factor = int(self.quality_factor_var.get())
        transparency_threshold = int(self.transparency_threshold_var.get())
        max_frames = self.max_frames_var.get()
        if max_frames == 0:
            max_frames = None # Tkinter IntVar 0 means "all frames" for us

        # Validar ruta del GIF
        if not gif_local_path:
            self.log_message("Error: Por favor, selecciona un archivo GIF.", 'error')
            self.convert_button.config(state=tk.NORMAL)
            return
        if not os.path.exists(gif_local_path):
            self.log_message("Error: El archivo GIF seleccionado no existe.", 'error')
            self.convert_button.config(state=tk.NORMAL)
            return

        # Nombre del archivo de salida
        output_filename = os.path.basename(gif_local_path).rsplit('.', 1)[0] + "_drawaria_animation.json"
        
        # Ejecutar la conversión en un hilo separado
        threading.Thread(target=self._run_conversion, args=(
            gif_local_path, output_filename, (output_width, output_height),
            brush_thickness, quality_factor, transparency_threshold, max_frames
        )).start()

    def _run_conversion(self, gif_local_path, output_filename, output_size, brush_thickness, quality_factor, transparency_threshold, max_frames):
        try:
            gif_to_drawaria_json_processor(
                gif_local_path,
                output_filename,
                output_size,
                brush_thickness,
                quality_factor,
                transparency_threshold,
                max_frames,
                self.log_message # Pasamos el callback para log
            )
        except Exception as e:
            self.log_message(f"Ocurrió un error inesperado durante la conversión: {e}", 'error')
        finally:
            # FIX 2: Correctly pass the config method call to after
            self.master.after(0, lambda: self.convert_button.config(state=tk.NORMAL)) # Habilitar botón de nuevo en el hilo principal

# --- Punto de entrada de la aplicación ---
if __name__ == "__main__":
    root = tk.Tk()
    app = GIFConverterApp(root)
    root.mainloop()
