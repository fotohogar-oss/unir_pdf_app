# Webapp en Flask para unir dos o más archivos PDF con:
# - Lista de archivos subidos
# - Posibilidad de reordenar
# - Pantalla de resultado con barra de "progreso"
# - Guardado del PDF en carpeta local
#
# Requisitos:
#    python -m pip install flask PyPDF2
#
# Uso:
#    cd C:\unir_pdf_app
#    python app.py
#    Luego abrir en el navegador: http://127.0.0.1:5000


import os
from io import BytesIO

from flask import (
    Flask,
    request,
    send_file,
    render_template_string,
    flash,
    redirect,
    url_for,
    session,
)

from PyPDF2 import PdfMerger

# --- CONFIGURACIÓN BÁSICA ---
app = Flask(__name__)
app.secret_key = "cambia_esta_clave_por_una_tuya"  # necesaria para session y mensajes

# Carpeta donde se guardarán los PDFs unificados
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), "salida")
os.makedirs(OUTPUT_FOLDER, exist_ok=True)  # crea la carpeta si no existe

# --- PLANTILLA HTML: PÁGINA PRINCIPAL (FORMULARIO) ---
HTML_INDEX = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>Unir archivos PDF</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link
      href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
      rel="stylesheet"
    >
    <style>
      body { background-color: #f5f5f5; }
      .container {
        max-width: 800px;
        margin-top: 40px;
        background: white;
        padding: 25px 30px;
        border-radius: 10px;
        box-shadow: 0 0 15px rgba(0,0,0,0.08);
      }
      .header-icon { font-size: 40px; }
      .file-table { font-size: 0.9rem; }
    </style>
</head>
<body>
<div class="container">
    <div class="text-center mb-4">
        <div class="header-icon">📎</div>
        <h2 class="mt-2">Unir archivos PDF</h2>
        <p class="text-muted mb-0">
            Sube dos o más archivos PDF, ajusta el orden y genera un solo documento.
        </p>
    </div>

    {% with messages = get_flashed_messages() %}
      {% if messages %}
        <div class="alert alert-warning">
          {% for msg in messages %}
            <div>{{ msg }}</div>
          {% endfor %}
        </div>
      {% endif %}
    {% endwith %}

    <form id="mainForm" method="post" enctype="multipart/form-data" class="mb-3">
        <div class="mb-3">
            <label for="pdfs" class="form-label"><strong>Archivos PDF</strong></label>
            <input
              class="form-control"
              type="file"
              id="pdfs"
              name="pdfs"
              multiple
              required
              accept="application/pdf"
            >
            <div class="form-text">
                Mantén presionada la tecla <b>Ctrl</b> (o <b>Cmd</b> en Mac) para seleccionar varios archivos.
                El orden inicial será el orden de selección, pero puedes ajustarlo abajo.
            </div>
        </div>

        <div id="lista-archivos" class="mb-3" style="display:none;">
            <label class="form-label"><strong>Orden de los archivos</strong></label>
            <div class="table-responsive">
              <table class="table table-sm table-bordered align-middle file-table">
                <thead class="table-light">
                  <tr>
                    <th>#</th>
                    <th>Nombre del archivo</th>
                    <th>Orden</th>
                  </tr>
                </thead>
                <tbody id="fileTableBody">
                  <!-- Se llena con JavaScript -->
                </tbody>
              </table>
            </div>
            <div class="form-text">
              Puedes cambiar el número de <b>Orden</b> para reordenar los PDFs.  
              Por ejemplo: pon 1 al que quieres primero, 2 al siguiente, etc.
            </div>
        </div>

        <div class="mb-3">
            <label for="output_name" class="form-label"><strong>Nombre del archivo resultante</strong></label>
            <input
              type="text"
              class="form-control"
              id="output_name"
              name="output_name"
              placeholder="Ejemplo: documentos_unidos.pdf"
            >
            <div class="form-text">
                Si lo dejas en blanco, se usará <code>PDF_unido.pdf</code>.
            </div>
        </div>

        <button type="submit" class="btn btn-primary w-100">
            ✅ Unir PDFs
        </button>
    </form>

    <hr>
    <h5>Instrucciones rápidas</h5>
    <ul>
        <li>Selecciona dos o más archivos PDF.</li>
        <li>Revisa la tabla y ajusta el <b>Orden</b> si es necesario.</li>
        <li>Escribe el nombre del archivo final (opcional).</li>
        <li>Haz clic en <b>“Unir PDFs”</b>.</li>
        <li>En la pantalla siguiente podrás descargar el PDF unido.</li>
    </ul>

    <p class="text-muted mt-3" style="font-size: 0.85rem;">
        Desarrollado en Python + Flask.
    </p>
</div>

<script>
  // Cuando el usuario selecciona archivos, llenamos la tabla con sus nombres
  const inputArchivos = document.getElementById('pdfs');
  const listaArchivosDiv = document.getElementById('lista-archivos');
  const tbody = document.getElementById('fileTableBody');
  const form = document.getElementById('mainForm');

  inputArchivos.addEventListener('change', function() {
    const files = Array.from(this.files);
    tbody.innerHTML = "";

    if (files.length === 0) {
        listaArchivosDiv.style.display = "none";
        return;
    }

    listaArchivosDiv.style.display = "block";

    files.forEach((file, index) => {
        const tr = document.createElement('tr');

        tr.innerHTML = `
          <td>${index + 1}</td>
          <td>${file.name}</td>
          <td style="width:120px;">
            <input
              type="number"
              class="form-control form-control-sm"
              name="order_${index}"
              value="${index + 1}"
              min="1"
              max="${files.length}"
              required
            >
          </td>
        `;

        tbody.appendChild(tr);
    });
  });

  // Validación antes de enviar el formulario:
  // - No permitir números de orden repetidos
  // - No permitir campos vacíos o fuera de rango
  form.addEventListener('submit', function(e) {
    const orderInputs = form.querySelectorAll('input[name^="order_"]');

    if (orderInputs.length === 0) {
      // por si acaso
      return;
    }

    const values = [];
    const used = new Set();
    let max = orderInputs.length;
    let errorMsg = "";

    for (const inp of orderInputs) {
      const valStr = inp.value.trim();
      const val = parseInt(valStr, 10);

      if (isNaN(val)) {
        errorMsg = "Todos los campos de orden deben ser números.";
        break;
      }
      if (val < 1 || val > max) {
        errorMsg = "Los números de orden deben estar entre 1 y " + max + ".";
        break;
      }
      if (used.has(val)) {
        errorMsg = "No puede haber números de orden repetidos. Revisa la tabla.";
        break;
      }
      used.add(val);
      values.push(val);
    }

    if (errorMsg !== "") {
      e.preventDefault(); // detener el envío
      alert(errorMsg);    // mensaje rápido al usuario
    }
  });
</script>

</body>
</html>
"""

# --- PLANTILLA HTML: PÁGINA DE RESULTADO ---
HTML_RESULTADO = """
<!doctype html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <title>PDF unido - Resultado</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link
      href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
      rel="stylesheet"
    >
    <style>
      body { background-color: #f5f5f5; }
      .container {
        max-width: 800px;
        margin-top: 40px;
        background: white;
        padding: 25px 30px;
        border-radius: 10px;
        box-shadow: 0 0 15px rgba(0,0,0,0.08);
      }
    </style>
</head>
<body>
<div class="container">
    <h3 class="mb-3">✅ PDF unido correctamente</h3>

    <p>Se procesaron {{ total_archivos }} archivo(s) PDF.</p>

    <h5>Progreso</h5>
    <div class="progress mb-3">
      <div
        class="progress-bar progress-bar-striped bg-success"
        role="progressbar"
        style="width: 100%;"
        aria-valuenow="100"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        {{ total_archivos }} de {{ total_archivos }} archivos procesados
      </div>
    </div>

    <h5>Orden final de los archivos</h5>
    <ol>
      {% for nombre in nombres_archivos %}
        <li>{{ nombre }}</li>
      {% endfor %}
    </ol>

    <div class="mb-3">
      <a href="{{ url_for('descargar') }}" class="btn btn-primary">
        ⬇️ Descargar PDF unificado ({{ nombre_salida }})
      </a>
    </div>

    <h5>Ubicación del archivo en tu equipo (servidor local)</h5>
    <p>
      El archivo fue guardado en esta carpeta del equipo donde corre la app:
    </p>
    <pre style="background:#f8f9fa; padding:10px; border-radius:5px;">{{ ruta_completa }}</pre>

    <p class="mb-1"><strong>En Windows</strong> puedes abrir la carpeta así:</p>
    <pre style="background:#f8f9fa; padding:10px; border-radius:5px;">explorer "{{ carpeta_salida }}"</pre>

    <p class="text-muted mt-4" style="font-size: 0.85rem;">
        Nota: Por seguridad del navegador, la aplicación web no puede abrir directamente el Explorador de archivos,
        pero puedes copiar la ruta y abrirla manualmente.
    </p>

    <a href="{{ url_for('index') }}" class="btn btn-link mt-2">⬅️ Volver a unir más PDFs</a>
</div>
</body>
</html>
"""


# --- RUTAS ---

@app.route("/", methods=["GET", "POST"])
def index():
    """
    Página principal:
      - GET: muestra el formulario.
      - POST: recibe los archivos, respeta el orden indicado y genera el PDF unido,
              luego redirige a la página de resultado.
    """
    if request.method == "GET":
        return render_template_string(HTML_INDEX)

    # POST: el usuario hizo clic en "Unir PDFs"
    archivos = request.files.getlist("pdfs")
    archivos_validos = [f for f in archivos if f and f.filename.lower().endswith(".pdf")]

    if len(archivos_validos) < 2:
        flash("Debes seleccionar al menos dos archivos PDF válidos.")
        return redirect(url_for("index"))

    # Leer órdenes desde el formulario: order_0, order_1, ...
    ordenados = []
    for idx, f in enumerate(archivos_validos):
        campo = f"order_{idx}"
        orden_str = request.form.get(campo, "").strip()
        try:
            orden = int(orden_str)
        except ValueError:
            # Si algo raro viene, usamos el orden original
            orden = idx + 1
        ordenados.append((orden, f))

    # --- Validación extra en el servidor para evitar órdenes repetidos o inválidos ---
    ordenes = [o for o, _ in ordenados]
    max_esperado = len(ordenes)

    # ¿Algún duplicado?
    if len(set(ordenes)) != len(ordenes):
        flash("Se detectaron números de orden repetidos. Ajusta la tabla y vuelve a intentar.")
        return redirect(url_for("index"))

    # ¿Algún orden fuera del rango 1..N?
    if any(o < 1 or o > max_esperado for o in ordenes):
        flash(f"Los números de orden deben estar entre 1 y {max_esperado}.")
        return redirect(url_for("index"))

    # Si todo está bien, ordenamos por el número que indicó el usuario
    ordenados.sort(key=lambda x: x[0])
    archivos_orden_final = [f for _, f in ordenados]
    nombres_finales = [f.filename for f in archivos_orden_final]

    # Nombre de salida
    output_name = request.form.get("output_name", "").strip()
    if not output_name:
        output_name = "PDF_unido.pdf"
    elif not output_name.lower().endswith(".pdf"):
        output_name += ".pdf"

    # Unir PDFs
    merger = PdfMerger()
    try:
        for f in archivos_orden_final:
            merger.append(f)

        # Guardar en memoria y también en disco
        buffer_pdf = BytesIO()
        merger.write(buffer_pdf)
        merger.close()
        buffer_pdf.seek(0)

        # Guardar en carpeta salida
        output_path = os.path.join(OUTPUT_FOLDER, output_name)
        with open(output_path, "wb") as f_out:
            f_out.write(buffer_pdf.getbuffer())

    except Exception as e:
        merger.close()
        flash(f"Ocurrió un error al unir los archivos: {e}")
        return redirect(url_for("index"))

    # Guardar datos en sesión para usarlos en la página de resultado
    session["output_name"] = output_name
    session["output_path"] = output_path
    session["nombres_archivos"] = nombres_finales

    return redirect(url_for("resultado"))


@app.route("/resultado")
def resultado():
    """
    Muestra información del proceso: lista de archivos, "barra de progreso",
    ruta donde quedó guardado el PDF y botón para descargar.
    """
    output_name = session.get("output_name")
    output_path = session.get("output_path")
    nombres_archivos = session.get("nombres_archivos", [])

    if not output_name or not output_path:
        flash("No se encontró información del último archivo generado.")
        return redirect(url_for("index"))

    carpeta_salida = os.path.dirname(output_path)
    total_archivos = len(nombres_archivos)

    return render_template_string(
        HTML_RESULTADO,
        total_archivos=total_archivos,
        nombres_archivos=nombres_archivos,
        nombre_salida=output_name,
        ruta_completa=output_path,
        carpeta_salida=carpeta_salida,
    )


@app.route("/descargar")
def descargar():
    """
    Envía el archivo unificado al navegador para que el usuario lo descargue.
    """
    output_name = session.get("output_name")
    output_path = session.get("output_path")

    if not output_name or not output_path or not os.path.exists(output_path):
        flash("No se encontró el archivo unificado para descargar.")
        return redirect(url_for("index"))

    return send_file(
        output_path,
        as_attachment=True,
        download_name=output_name,
        mimetype="application/pdf",
    )

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)


#if __name__ == "__main__":
#Ejecutar la app en modo desarrollo
#app.run(debug=True, host="127.0.0.1", port=5000)

#if __name__ == "__main__":
#    app.run(debug=False, host="0.0.0.0", port=5000)

