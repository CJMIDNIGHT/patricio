document.addEventListener("DOMContentLoaded", () => {
  const editarDatosButton = document.querySelector('[data-bs-target="#editarDatosModal"]');
  const editarDatosPopup = document.getElementById("editarDatosPopup");
  const guardarDatosButton = document.getElementById("guardarDatos");
  const cancelarEdicionButton = document.getElementById("cancelarEdicion");

  const inputsCard = {
    nombre: document.getElementById("nombre"),
    apellido: document.getElementById("apellido"),
    codigo_aula: document.getElementById("codigo_aula"),
    correo: document.getElementById("correo"),
    telefono: document.getElementById("telefono"),
  };

  const inputsPopup = {
    nombre: document.getElementById("popupNombre"),
    apellido: document.getElementById("popupApellido"),
    codigo_aula: document.getElementById("popupCodigoAula"),
    correo: document.getElementById("popupCorreo"),
    telefono: document.getElementById("popupTelefono"),
  };

  Object.values(inputsCard).forEach((input) => {
    if (input) input.disabled = true;
  });

  if (editarDatosButton && editarDatosPopup) {
    editarDatosButton.addEventListener("click", () => {
      Object.keys(inputsCard).forEach((key) => {
        if (inputsPopup[key] && inputsCard[key]) {
          inputsPopup[key].value = inputsCard[key].value;
        }
      });
      editarDatosPopup.style.display = "flex";
    });
  }

  if (guardarDatosButton) {
    guardarDatosButton.addEventListener("click", () => {
      Object.keys(inputsCard).forEach((key) => {
        if (inputsPopup[key] && inputsCard[key]) {
          inputsCard[key].value = inputsPopup[key].value;
        }
      });
      alert("Datos guardados correctamente.");
      editarDatosPopup.style.display = "none";
    });
  }

  if (cancelarEdicionButton) {
    cancelarEdicionButton.addEventListener("click", () => {
      editarDatosPopup.style.display = "none";
    });
  }

  const notificacionesButton = document.querySelector('[data-bs-target="#notificacionesModal"]');
  const notificacionesPopup = document.getElementById("notificacionesPopup");
  const cerrarNotificacionesButton = document.getElementById("cerrarNotificaciones");
  const notificacionesLista = document.getElementById("notificacionesLista");

  const verificarNotificaciones = () => {
    if (!notificacionesLista) return;
    if (notificacionesLista.querySelectorAll("li:not(.fija)").length === 0) {
      const ya = notificacionesLista.querySelector(".sin-notificaciones");
      if (!ya) {
        notificacionesLista.innerHTML += '<li class="sin-notificaciones">No hay notificaciones nuevas</li>';
      }
    }
  };

  const tablaActividades = document.querySelector(".actividades-tabla tbody");

  const actualizarPrimeraNotificacion = () => {
    if (!notificacionesLista || !tablaActividades) return;
    const primeraNotificacion = notificacionesLista.querySelector("li span");
    if (!primeraNotificacion) return;

    const hoy = new Date();
    const filas = [];

    tablaActividades.querySelectorAll("tr").forEach((fila) => {
      const celdas = fila.querySelectorAll("td");
      if (celdas.length < 5) return;
      const nombre = celdas[2].textContent.trim();
      const fechaStr = celdas[4].textContent.trim();
      const partes = fechaStr.split("/").map((n) => parseInt(n, 10));
      if (partes.length < 3) return;
      const fecha = new Date(2000 + partes[2], partes[1] - 1, partes[0]);
      const dias = Math.ceil((fecha - hoy) / (1000 * 60 * 60 * 24));
      filas.push({ nombre, dias });
    });

    filas.sort((a, b) => a.dias - b.dias);
    const texto = filas.map((r) => `${r.nombre}: próxima revisión en ${r.dias} días`).join("<br>");
    primeraNotificacion.innerHTML = `<strong>Resumen de actividades:</strong><br>${texto}`;

    const primerBoton = notificacionesLista.querySelector("li .redirigir_notificacion_receta");
    if (primerBoton) {
      primerBoton.onclick = () => {
        notificacionesPopup.style.display = "none";
        document.getElementById("recetasPopup").style.display = "flex";
      };
    }
  };

  const generarNotificacionesActividades = () => {
    if (!notificacionesLista || !tablaActividades) return;
    notificacionesLista.querySelectorAll("li:not(.fija)").forEach((li) => li.remove());

    const hoy = new Date();
    tablaActividades.querySelectorAll("tr").forEach((fila) => {
      const celdas = fila.querySelectorAll("td");
      if (celdas.length < 5) return;

      const nombre = celdas[2].textContent.trim();
      const fechaStr = celdas[4].textContent.trim();
      const partes = fechaStr.split("/").map(Number);
      if (partes.length < 3) return;
      const fecha = new Date(2000 + partes[2], partes[1] - 1, partes[0]);
      const dias = Math.ceil((fecha - hoy) / (1000 * 60 * 60 * 24));

      if (dias <= 5 && dias >= 0) {
        const alerta = document.createElement("li");
        alerta.innerHTML = `
          <span style="color:${dias <= 1 ? "red" : dias <= 3 ? "orange" : "goldenrod"}">
            ¡Atención! «${nombre}» revisión en ${dias} días
          </span>
          <div class="popup-buttons">
            <button class="btn boton eliminar-notificacion"><i class="bi bi-trash"></i></button>
            <button class="btn boton redirigir_notificacion_receta"><i class="bi bi-arrow-right-circle"></i></button>
          </div>
        `;
        notificacionesLista.appendChild(alerta);
      }
    });

    document.querySelectorAll(".eliminar-notificacion").forEach((btn) => {
      btn.onclick = (e) => {
        const li = e.target.closest("li");
        if (li && !li.classList.contains("fija")) li.remove();
        verificarNotificaciones();
      };
    });

    document.querySelectorAll(".redirigir_notificacion_receta").forEach((btn) => {
      btn.onclick = () => {
        notificacionesPopup.style.display = "none";
        document.getElementById("recetasPopup").style.display = "flex";
      };
    });
  };

  if (notificacionesButton) {
    notificacionesButton.addEventListener("click", () => {
      notificacionesPopup.style.display = "flex";
      actualizarPrimeraNotificacion();
      generarNotificacionesActividades();
    });
  }

  if (cerrarNotificacionesButton) {
    cerrarNotificacionesButton.addEventListener("click", () => {
      notificacionesPopup.style.display = "none";
    });
  }

  document.querySelectorAll(".redirigir_notificacion_receta").forEach((btn) => {
    btn.addEventListener("click", () => {
      notificacionesPopup.style.display = "none";
      document.getElementById("recetasPopup").style.display = "flex";
    });
  });

  document.querySelectorAll(".redirigir_notificacion_compra").forEach((btn) => {
    btn.addEventListener("click", () => {
      notificacionesPopup.style.display = "none";
      document.getElementById("comprasPopup").style.display = "flex";
    });
  });

  const recetasButton = document.querySelector('[data-bs-target="#recetasModal"]');
  const recetasPopup = document.getElementById("recetasPopup");
  const cerrarRecetasButton = document.getElementById("cerrarRecetas");

  if (recetasButton) {
    recetasButton.addEventListener("click", () => {
      recetasPopup.style.display = "flex";
    });
  }

  if (cerrarRecetasButton) {
    cerrarRecetasButton.addEventListener("click", () => {
      recetasPopup.style.display = "none";
    });
  }

  const historialButton = document.querySelector('[data-bs-target="#historialModal"]');
  const comprasPopup = document.getElementById("comprasPopup");
  const cerrarHistorialButton = document.getElementById("cerrarHistorial");

  if (historialButton) {
    historialButton.addEventListener("click", () => {
      comprasPopup.style.display = "flex";
    });
  }

  if (cerrarHistorialButton) {
    cerrarHistorialButton.addEventListener("click", () => {
      comprasPopup.style.display = "none";
    });
  }

  document.querySelectorAll(".editar-fecha-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const fila = btn.closest("tr");
      const celdas = fila.querySelectorAll("td");
      if (celdas.length < 5) return;

      const celdaFecha = celdas[4];
      const fechaActual = celdaFecha.textContent.trim();
      const nuevaFecha = prompt("Introduce nueva fecha de revisión (DD/MM/AA):", fechaActual);

      if (nuevaFecha && /^\d{2}\/\d{2}\/\d{2}$/.test(nuevaFecha)) {
        celdaFecha.textContent = nuevaFecha;
        alert("Fecha actualizada: " + nuevaFecha);
        actualizarPrimeraNotificacion();
        generarNotificacionesActividades();
      } else if (nuevaFecha) {
        alert("Formato incorrecto. Usa DD/MM/AA");
      }
    });
  });

  actualizarPrimeraNotificacion();
  generarNotificacionesActividades();
});
