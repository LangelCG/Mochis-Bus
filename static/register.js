document.addEventListener('DOMContentLoaded', function() {
    
    const registerForm = document.getElementById('register-form');

    if (registerForm) {
        registerForm.addEventListener('submit', async function(event) {
            event.preventDefault(); 
            
            // 1. SELECCIONAR EL BOTÓN Y BLOQUEARLO
            const boton = document.querySelector('.login-button');
            const textoOriginal = boton.innerText; // Guardamos "REGISTRARME"
            
            boton.disabled = true;
            boton.innerText = "Procesando...";
            boton.style.backgroundColor = "#ccc"; // Gris para que se vea desactivado
            boton.style.cursor = "not-allowed";

            // Obtenemos valores
            const username = document.getElementById('username').value;
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;

            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ 
                        username: username, 
                        email: email,
                        password: password 
                    }),
                });

                const data = await response.json();

                if (data.success) {
                    // Si fue rápido, mostramos el mensaje y redireccionamos
                    alert(data.message); 
                    window.location.href = '/'; 
                } else {
                    // Si hubo error, reactivamos el botón
                    alert(data.message);
                    reactivarBoton(boton, textoOriginal);
                }
            } catch (error) {
                console.error(error);
                alert("Error de conexión con el servidor.");
                reactivarBoton(boton, textoOriginal);
            }
        });
    }

    // Función auxiliar para regresar el botón a la normalidad
    function reactivarBoton(btn, texto) {
        btn.disabled = false;
        btn.innerText = texto;
        btn.style.backgroundColor = "#007bff"; // Azul original
        btn.style.cursor = "pointer";
    }
});