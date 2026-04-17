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

  // Login
  if (loginBtn) {
    loginBtn.addEventListener("click", () => {
      const username = document.getElementById("username").value;
      const password = document.getElementById("password").value;
      const errorMessage = document.getElementById("errorMessage");

      if (username === "admin" && password === "1234") {
        errorMessage.style.display = "none";
        alert("Inicio de sesión exitoso ✅");
        window.location.href = "admin.html";
      } else if (username === "educador" && password === "1234") {
        errorMessage.style.display = "none";
        alert("Inicio de sesión exitoso ✅");
        window.location.href = "empleado.html";
      } else if (
        (username === "familia" || username === "usuario") &&
        password === "1234"
      ) {
        errorMessage.style.display = "none";
        alert("Inicio de sesión exitoso ✅");
        window.location.href = "usuario.html";
      } else {
        errorMessage.textContent = "Usuario o contraseña incorrectos";
        errorMessage.style.display = "block";
      }
    });
  }

  // Registro
  if (registerBtn) {
    registerBtn.addEventListener("click", () => {
      const pass1 = document.getElementById("password1").value;
      const pass2 = document.getElementById("password2").value;
      const errorMsg = document.getElementById("registroError");

      const regex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/;

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

      errorMsg.textContent = "";
      alert("Registro exitoso ✅");
      registerModal.style.display = "none";
      loginModal.style.display = "flex";
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
