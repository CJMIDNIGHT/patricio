function patricioApiBase() {
  return `http://${window.location.hostname}:5000`;
}

const PATRICIO_USER_KEY = "patricio_usuario";

function guardarSesionUsuario(usuario) {
  try {
    sessionStorage.setItem(PATRICIO_USER_KEY, JSON.stringify(usuario));
  } catch (_) {}
}

document.addEventListener("DOMContentLoaded", () => {
  // Modales
  const loginModal = document.getElementById("loginModal");
  const registerModal = document.getElementById("registerModal");

  // Botones
  const userIcon = document.getElementById("userIcon");
  const loginLink = document.getElementById("loginLink");
  const closeModal = document.getElementById("closeModal");
  const closeRegister = document.getElementById("closeRegister");
  const loginBtn = document.getElementById("loginBtn");
  const registerBtn = document.getElementById("registerBtn");

  // Abrir login
  if (userIcon) {
    userIcon.addEventListener("click", () => {
      loginModal.style.display = "flex";
    });
  }
  if (loginLink) {
    loginLink.addEventListener("click", () => {
      loginModal.style.display = "flex";
    });
  }

  // Cerrar login
  if (closeModal) {
    closeModal.addEventListener("click", () => {
      loginModal.style.display = "none";
    });
  }
  if (loginModal) {
    window.addEventListener("click", (e) => {
      if (e.target === loginModal) loginModal.style.display = "none";
    });
  }

  // Abrir registro
  if (document.getElementById("openRegister")) {
    document.getElementById("openRegister").addEventListener("click", () => {
      if (registerModal) {
        registerModal.style.display = "flex";
      }
    });
  }

  // Cerrar registro
  if (closeRegister) {
    closeRegister.addEventListener("click", () => {
      if (registerModal) {
        registerModal.style.display = "none";
      }
    });
  }
  if (registerModal) {
    window.addEventListener("click", (e) => {
      if (e.target === registerModal) registerModal.style.display = "none";
    });
  }

  // Login (API + MySQL)
  if (loginBtn) {
    loginBtn.addEventListener("click", async () => {
      const username = (document.getElementById("username")?.value || "").trim();
      const password = document.getElementById("password")?.value || "";
      const errorMessage = document.getElementById("errorMessage");

      if (!username || !password) {
        if (errorMessage) {
          errorMessage.textContent = "Introduce email y contraseña.";
          errorMessage.style.display = "block";
        }
        return;
      }

      loginBtn.disabled = true;
      try {
        const res = await fetch(`${patricioApiBase()}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            email: username,
            contrasena: password,
          }),
        });
        const data = await res.json().catch(() => ({}));

        if (!data.ok || !data.usuario) {
          if (errorMessage) {
            errorMessage.textContent =
              data.error || "Usuario o contraseña incorrectos";
            errorMessage.style.display = "block";
          }
          return;
        }

        guardarSesionUsuario(data.usuario);
        if (errorMessage) errorMessage.style.display = "none";

        const rol = data.usuario.rol;
        let destino = "index.html";
        if (rol === "admin") destino = "admin.html";
        else if (rol === "educador") destino = "empleado.html";
        else if (rol === "familia") destino = "usuario.html";

        alert("Inicio de sesión exitoso ✅");
        window.location.href = destino;
      } catch (e) {
        console.warn(e);
        if (errorMessage) {
          errorMessage.textContent =
            "No se pudo conectar con la API (¿servidor en :5000 encendido?).";
          errorMessage.style.display = "block";
        }
      } finally {
        loginBtn.disabled = false;
      }
    });
  }

  // Registro (API: rol familia)
  if (registerBtn) {
    registerBtn.addEventListener("click", async () => {
      const nombre = (document.getElementById("nombre")?.value || "").trim();
      const apellido = (document.getElementById("apellido")?.value || "").trim();
      const correo = (document.getElementById("email")?.value || "").trim();
      const pass1 = document.getElementById("password1")?.value || "";
      const pass2 = document.getElementById("password2")?.value || "";
      const errorMsg = document.getElementById("registroError");

      const regex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/;

      if (!nombre || !apellido || !correo) {
        errorMsg.textContent = "Nombre, apellidos y correo son obligatorios.";
        return;
      }

      if (!pass1 || !pass2) {
        errorMsg.textContent = "Por favor, rellena ambos campos de contraseña.";
        return;
      }

      if (pass1 !== pass2) {
        errorMsg.textContent = "Las contraseñas no coinciden.";
        return;
      }

      if (!regex.test(pass1)) {
        errorMsg.textContent = "La contraseña no cumple los requisitos.";
        return;
      }

      registerBtn.disabled = true;
      errorMsg.textContent = "";

      try {
        const res = await fetch(`${patricioApiBase()}/api/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({
            nombre,
            apellido,
            correo,
            contrasena: pass1,
          }),
        });
        const data = await res.json().catch(() => ({}));

        if (!data.ok || !data.usuario) {
          errorMsg.textContent =
            data.error ||
            "No se pudo completar el registro. ¿Correo o usuario repetido?";
          return;
        }

        guardarSesionUsuario(data.usuario);
        alert(
          `Registro exitoso ✅\nAccede con tu email: ${data.usuario.email || data.usuario.correo}`
        );
        registerModal.style.display = "none";
        if (loginModal) loginModal.style.display = "flex";
      } catch (e) {
        console.warn(e);
        errorMsg.textContent =
          "Sin conexión con la API (¿servidor en :5000 encendido?).";
      } finally {
        registerBtn.disabled = false;
      }
    });
  }

  // Cerrar sesión
  const logoutButton = document.getElementById("logoutButton");
  const logoutPopup = document.getElementById("logoutPopup");
  const confirmLogout = document.getElementById("confirmLogout");
  const cancelLogout = document.getElementById("cancelLogout");

  // Verifica si los elementos existen antes de añadir los eventos
  if (logoutButton && logoutPopup) {
    // Mostrar el popup al hacer clic en el botón de logout
    logoutButton.addEventListener("click", () => {
      logoutPopup.style.display = "flex";
    });
  }

  // Redirigir a index.html al hacer clic en "Sí"
  if (confirmLogout) {
    confirmLogout.addEventListener("click", () => {
      try {
        sessionStorage.removeItem(PATRICIO_USER_KEY);
        localStorage.removeItem('ros_address');  // ← add this
      } catch (_) {}
      window.location.href = "index.html";
    });
  }

  // Cerrar el popup al hacer clic en "No"
  if (cancelLogout) {
    cancelLogout.addEventListener("click", () => {
      logoutPopup.style.display = "none";
    });
  }
});
