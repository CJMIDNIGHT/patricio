document.addEventListener("DOMContentLoaded", () => {
  const popup = document.getElementById("añadirProductoPopup");
  const guardarBtn = document.getElementById("guardarProducto");
  const cancelarBtn = document.getElementById("cancelarAñadirProducto");
  const tabla = document.querySelector(".stock-tabla tbody");

  // Abrir el popup
  document.querySelector('[data-bs-target="#añadirProducto"]').addEventListener("click", () => {
    popup.style.display = "flex";
  });

  // Cerrar el popup
  cancelarBtn.addEventListener("click", () => {
    popup.style.display = "none";
  });

  // Guardar el producto
  guardarBtn.addEventListener("click", () => {
    const codigo = document.getElementById("codigoProducto").value;
    const nombre = document.getElementById("nombreProducto").value;
    const categoria = document.getElementById("categoriaProducto").value;
    const cantidad = document.getElementById("cantidadProducto").value;
    const ubicacion = document.getElementById("ubicacionProducto").value;
    const fechaVencimiento = document.getElementById("fechaVencimientoProducto").value;

    if (codigo && nombre && categoria && cantidad && ubicacion && fechaVencimiento) {
      // Formatear la fecha al formato DD/MM/YYYY
      const fechaFormateada = new Date(fechaVencimiento).toLocaleDateString("es-ES", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      });

      // Crear una nueva fila
      const nuevaFila = document.createElement("tr");
      nuevaFila.innerHTML = `
        <td>${codigo}</td>
        <td>${nombre}</td>
        <td>${categoria}</td>
        <td>${cantidad}</td>
        <td>${ubicacion}</td>
        <td>${fechaFormateada}</td>
      `;

      // Añadir la fila a la tabla
      tabla.appendChild(nuevaFila);

      // Cerrar el popup y limpiar el formulario
      popup.style.display = "none";
      document.getElementById("añadirProductoForm").reset();
    } else {
      alert("Por favor, completa todos los campos.");
    }
  });

  const eliminarPopup = document.getElementById("eliminarProductoPopup");
  const confirmarEliminarBtn = document.getElementById("confirmarEliminarProducto");
  const cancelarEliminarBtn = document.getElementById("cancelarEliminarProducto");

  // Abrir el popup para eliminar producto
  document.querySelector('[data-bs-target="#eliminarProducto"]').addEventListener("click", () => {
    eliminarPopup.style.display = "flex";
  });

  // Cerrar el popup
  cancelarEliminarBtn.addEventListener("click", () => {
    eliminarPopup.style.display = "none";
  });

  // Confirmar eliminación del producto
  confirmarEliminarBtn.addEventListener("click", () => {
    const codigoEliminar = document.getElementById("codigoEliminar").value;

    if (codigoEliminar) {
      let productoEliminado = false;

      // Buscar y eliminar la fila con el código especificado
      Array.from(tabla.rows).forEach((fila) => {
        if (fila.cells[0].textContent === codigoEliminar) {
          tabla.removeChild(fila);
          productoEliminado = true;
        }
      });

      if (productoEliminado) {
        alert(`Material con código ${codigoEliminar} eliminado del inventario.`);
      } else {
        alert(`No se encontró material con el código ${codigoEliminar}.`);
      }

      // Cerrar el popup y limpiar el campo
      eliminarPopup.style.display = "none";
      document.getElementById("eliminarProductoForm").reset();
    } else {
      alert("Por favor, ingresa un código válido.");
    }
  });

  // --- Modificar Cantidad ---
  const modificarPopup = document.getElementById("modificarProductoPopup");
  const confirmarModificarBtn = document.getElementById("confirmarModificarProducto");
  const cancelarModificarBtn = document.getElementById("cancelarModificarProducto");

  // Abrir el popup para modificar cantidad
  document.querySelector('[data-bs-target="#modificarProducto"]').addEventListener("click", () => {
    modificarPopup.style.display = "flex";
  });

  // Cerrar el popup
  cancelarModificarBtn.addEventListener("click", () => {
    modificarPopup.style.display = "none";
  });

  // Confirmar modificación de la cantidad
  confirmarModificarBtn.addEventListener("click", () => {
    const codigoModificar = document.getElementById("codigoModificar").value;
    const accionModificar = document.getElementById("accionModificar").value;
    const cantidadModificar = parseInt(document.getElementById("cantidadModificar").value, 10);

    if (codigoModificar && accionModificar && cantidadModificar) {
      let productoModificado = false;

      // Buscar y modificar la cantidad del producto
      Array.from(tabla.rows).forEach((fila) => {
        if (fila.cells[0].textContent === codigoModificar) {
          let cantidadActual = parseInt(fila.cells[3].textContent, 10);

          // Modificar la cantidad según la acción seleccionada
          if (accionModificar === "añadir") {
            cantidadActual += cantidadModificar;
          } else if (accionModificar === "eliminar") {
            cantidadActual -= cantidadModificar;
            if (cantidadActual < 0) cantidadActual = 0; // Evitar cantidades negativas
          }

          fila.cells[3].textContent = cantidadActual; // Actualizar cantidad
          productoModificado = true;

          // Verificar si la cantidad final es menor o igual a 10
          if (cantidadActual <= 10) {
            generarNotificacionStock(codigoModificar, fila.cells[1].textContent); // Generar notificación
          }
        }
      });

      if (productoModificado) {
        alert(`Unidades del material ${codigoModificar} actualizadas.`);
      } else {
        alert(`No se encontró material con el código ${codigoModificar}.`);
      }

      // Cerrar el popup y limpiar el formulario
      modificarPopup.style.display = "none";
      document.getElementById("modificarProductoForm").reset();
    } else {
      alert("Por favor, completa todos los campos.");
    }
  });

  // Función para actualizar la cantidad de notificaciones en el botón
  function actualizarContadorNotificaciones() {
    const notificacionesLista = document.getElementById("notificacionesLista");
    const botonNotificaciones = document.getElementById("botonNotificaciones");
    const cantidadNotificaciones = notificacionesLista.children.length;

    // Actualizar el texto del botón con la cantidad de notificaciones
    botonNotificaciones.textContent = `MIS NOTIFICACIONES (${cantidadNotificaciones})`;
  }

  // Modificar la función `generarNotificacionStock` para actualizar el contador
  function generarNotificacionStock(codigo, nombre) {
    const notificacionesLista = document.getElementById("notificacionesLista");

    // Verificar si ya existe una notificación para este material
    const notificacionExistente = Array.from(notificacionesLista.children).find((notificacion) =>
      notificacion.textContent.includes(`Código: ${codigo}`)
    );

    if (!notificacionExistente) {
      // Crear una nueva notificación
      const notificacion = document.createElement("li");
      notificacion.classList.add("fija", "stock-notificacion");
      notificacion.innerHTML = `
        <span>El material «${nombre}» (código ${codigo}) tiene pocas unidades (menos de 10). Considera repuesto o rotación.</span>
        <div class="popup-buttons">
          <button class="btn boton eliminar-notificacion">
            <i class="bi bi-trash"></i> <!-- Icono de eliminar -->
          </button>
        </div>
      `;

      // Añadir la notificación a la lista
      notificacionesLista.appendChild(notificacion);

      // Agregar funcionalidad para eliminar la notificación
      notificacion.querySelector(".eliminar-notificacion").addEventListener("click", () => {
        notificacion.remove();
        actualizarContadorNotificaciones(); // Actualizar el contador al eliminar
      });

      // Actualizar el contador de notificaciones
      actualizarContadorNotificaciones();
    }
  }

  // Modificar la función `revisarStock` para actualizar el contador
  function revisarStock() {
    const tabla = document.querySelector(".stock-tabla tbody");
    const notificacionesLista = document.getElementById("notificacionesLista");

    // Limpiar notificaciones previas relacionadas con el stock
    Array.from(notificacionesLista.children).forEach((notificacion) => {
      if (notificacion.classList.contains("stock-notificacion")) {
        notificacion.remove();
      }
    });

    // Recorrer las filas de la tabla
    Array.from(tabla.rows).forEach((fila) => {
      const codigo = fila.cells[0].textContent; // Código del producto
      const nombre = fila.cells[1].textContent; // Nombre del producto
      const cantidad = parseInt(fila.cells[3].textContent, 10); // Cantidad disponible

      // Verificar si la cantidad es menor a 10
      if (cantidad < 10) {
        generarNotificacionStock(codigo, nombre);
      }
    });

    // Actualizar el contador de notificaciones
    actualizarContadorNotificaciones();
  }

  // Función para resaltar cantidades bajas
  function resaltarCantidadesBajas() {
    const tabla = document.querySelector(".stock-tabla tbody");

    // Verificar si la tabla existe
    if (!tabla) {
      console.error("No se encontró la tabla de materiales.");
      return;
    }

    // Recorrer las filas de la tabla
    Array.from(tabla.rows).forEach((fila) => {
      const cantidadCelda = fila.cells[3]; // Celda de la cantidad
      const cantidad = parseInt(cantidadCelda.textContent, 10);

      // Aplicar o quitar la clase según la cantidad
      if (cantidad < 10) {
        cantidadCelda.classList.add("cantidad-baja");
      } else {
        cantidadCelda.classList.remove("cantidad-baja");
      }
    });
  }

  // Llamar a la función al cargar la página
  document.addEventListener("DOMContentLoaded", () => {
    revisarStock();
    resaltarCantidadesBajas();
  });

  const notificacionesPopup = document.getElementById("notificacionesPopup");
  const cerrarNotificacionesBtn = document.getElementById("cerrarNotificaciones");
  // Botón y popup de entrega de medicamento
  document.addEventListener("DOMContentLoaded", function() {
    const btnEntrega = document.getElementById("botonEntregaMedicamento");
    const popupEntrega = document.getElementById("popupEntregaMedicamento");
    const cerrarEntrega = document.getElementById("cerrarPopupEntregaMedicamento");
    const imagenMedicamento = document.getElementById("imagenMedicamentoDetectado");
    const nombreClienteEntrega = document.getElementById("nombreClienteEntrega");

    if (btnEntrega && popupEntrega && cerrarEntrega) {
      btnEntrega.addEventListener("click", function() {
        // Aquí puedes actualizar dinámicamente la imagen y el nombre si lo necesitas
        // imagenMedicamento.src = "images/robot.png";
        // nombreClienteEntrega.textContent = "625932402";
        popupEntrega.style.display = "flex";
      });
      cerrarEntrega.addEventListener("click", function() {
        popupEntrega.style.display = "none";
      });
    }
  });
  // Abrir el popup de notificaciones
  document.querySelector('[data-bs-target="#notificacionesPopup"]').addEventListener("click", () => {
    notificacionesPopup.style.display = "flex";
  });

  // Cerrar el popup de notificaciones
  cerrarNotificacionesBtn.addEventListener("click", () => {
    notificacionesPopup.style.display = "none";
  });

  document.querySelector('[data-bs-target="#modificarInfoPopup"]').addEventListener("click", function(e) {
    e.preventDefault();
    document.getElementById("modificarInfoPopup").style.display = "flex";
});

  document.getElementById("cancelarModificarInfo").addEventListener("click", function() {
    document.getElementById("modificarInfoPopup").style.display = "none";
});

  const ventas = [
    {
      codigo: "SES-12",
      fecha: "21/05/2026",
      hora: "10:15",
      idNino: "NINO-042",
      actividad: "Colores con Patricio",
      participantes: 8,
      notas: "Muy participativos",
    },
    {
      codigo: "SES-13",
      fecha: "21/05/2026",
      hora: "11:30",
      idNino: "GRUPO-A",
      actividad: "Cuenta y mueve",
      participantes: 12,
      notas: "En grupo",
    },
  ];

  function mostrarVentas() {
    const ventasTablaBody = document.getElementById("ventasTablaBody");
    ventasTablaBody.innerHTML = "";
    ventas.forEach((v) => {
      ventasTablaBody.innerHTML += `
        <tr>
          <td>${v.codigo}</td>
          <td>${v.fecha}</td>
          <td>${v.hora}</td>
          <td>${v.idNino}</td>
          <td>${v.actividad}</td>
          <td>${v.participantes}</td>
          <td>${v.notas}</td>
        </tr>
      `;
    });
  }

  const registroVentasPopup = document.getElementById("registroVentasPopup");
  const cerrarRegistroVentasBtn = document.getElementById("cerrarRegistroVentas");
  const abrirRegistroVentasBtn = document.getElementById("botonRegistroVentas");

  abrirRegistroVentasBtn.addEventListener("click", (e) => {
    e.preventDefault();
    registroVentasPopup.style.display = "flex";
    mostrarVentas();
  });

  cerrarRegistroVentasBtn.addEventListener("click", () => {
    registroVentasPopup.style.display = "none";
  });

  const popupRecetasCliente = document.getElementById("popupRecetasCliente");
  const botonRecetasCliente = document.getElementById("botonRecetasCliente");
  const cerrarPopupRecetasCliente = document.getElementById("cerrarPopupRecetasCliente");
  const formBuscarRecetas = document.getElementById("formBuscarRecetas");
  const tablaRecetasClienteBody = document.getElementById("tablaRecetasClienteBody");

  const actividadesPorId = {
    NINO042: [
      { denominacion: "Cuentos rimados (pack)", codigo: "001", cantidad: 1 },
      { denominacion: "Bloques lógicos", codigo: "003", cantidad: 1 },
    ],
    GRUPOA: [
      { denominacion: "Puzzle 12 piezas", codigo: "002", cantidad: 2 },
      { denominacion: "Figuras magnéticas", codigo: "004", cantidad: 1 },
    ],
    NINO015: [{ denominacion: "Memoria con dibujos", codigo: "005", cantidad: 1 }],
  };

  // Abrir popup
  botonRecetasCliente.addEventListener("click", () => {
    popupRecetasCliente.style.display = "flex";
    tablaRecetasClienteBody.innerHTML = "";
  });

  // Cerrar popup
  cerrarPopupRecetasCliente.addEventListener("click", () => {
    popupRecetasCliente.style.display = "none";
  });

  formBuscarRecetas.addEventListener("submit", (e) => {
    e.preventDefault();
    const raw = document.getElementById("inputSipRecetas").value.trim();
    const clave = raw.replace(/[^a-zA-Z0-9]/g, "").toUpperCase();
    const recetas = actividadesPorId[clave] || [];
    tablaRecetasClienteBody.innerHTML = "";

    if (recetas.length === 0) {
      tablaRecetasClienteBody.innerHTML = `<tr><td colspan="4">No hay actividades registradas para ese identificador. Prueba: NINO-042, GRUPO-A o NINO-015.</td></tr>`;
      return;
    }

    recetas.forEach((receta) => {
      let stock = "NO";
      Array.from(document.querySelectorAll(".stock-tabla tbody tr")).forEach((fila) => {
        const nombre = fila.cells[1].textContent.trim().toLowerCase();
        if (nombre === receta.denominacion.trim().toLowerCase()) {
          const cantidad = parseInt(fila.cells[3].textContent, 10);
          if (cantidad > 0) stock = `<span style="color:green;font-weight:bold;">Sí</span>`;
          else stock = `<span style="color:red;font-weight:bold;">No</span>`;
        }
      });
      if (stock === "NO") stock = `<span style="color:red;font-weight:bold;">No</span>`;

      tablaRecetasClienteBody.innerHTML += `
        <tr>
          <td>${receta.denominacion}</td>
          <td>${receta.codigo}</td>
          <td>${receta.cantidad}</td>
          <td>${stock}</td>
        </tr>
      `;
    });
  });
});