document.addEventListener('DOMContentLoaded', function() {
    
    const loginForm = document.getElementById('login-form');

    if (loginForm) {
        loginForm.addEventListener('submit', async function(event) {
            
            event.preventDefault(); 
            
            // Referencia al botón para efectos visuales
            const botonLogin = loginForm.querySelector('button[type="submit"]');
            const textoOriginal = botonLogin.innerText;
            botonLogin.disabled = true;
            botonLogin.innerText = "Verificando...";

            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;

            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password }),
                });

                const data = await response.json();

                if (data.success) {
                    // --- NUEVO: Guardamos el rol para mostrarlo en el header ---
                    localStorage.setItem('mb_username', username); // Usamos prefijo mb_ para MochisBus

                    if (data.is_admin) {
                        localStorage.setItem('mb_role', 'Administrador');
                        window.location.href = '/admin_panel';
                    } 
                    else if (data.ruta_asignada) {
                        // Es chofer. Guardamos ruta y rol.
                        localStorage.setItem('chofer_nombre', username); // Mantenemos este para chofer.html
                        localStorage.setItem('chofer_ruta', data.ruta_asignada);
                        localStorage.setItem('mb_role', 'Conductor'); // Rol visible
                        window.location.href = '/soy_chofer';
                    } 
                    else {
                        localStorage.setItem('mb_role', 'Pasajero');
                        window.location.href = '/dashboard';
                    }
                } else {
                    alert(data.message);
                    botonLogin.disabled = false;
                    botonLogin.innerText = textoOriginal;
                }

            } catch (error) {
                console.error("Error:", error);
                alert("Error de conexión.");
                botonLogin.disabled = false;
                botonLogin.innerText = textoOriginal;
            }
        });
    }
});