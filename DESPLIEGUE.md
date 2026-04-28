# Guía de Despliegue en Render

## Paso 1 — Subir el código a GitHub

1. Ve a https://github.com y haz clic en **"New repository"**
2. Nombre sugerido: `restaurante-admin`
3. Déjalo **privado** (recomendado)
4. NO marques "Add README" ni nada extra, déjalo vacío
5. Haz clic en **"Create repository"**

Luego abre la carpeta del proyecto en la terminal (o CMD) y ejecuta:

```bash
git init
git add .
git commit -m "Sistema administrativo restaurante - versión inicial"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/restaurante-admin.git
git push -u origin main
```

Reemplaza `TU_USUARIO` con tu usuario de GitHub.

---

## Paso 2 — Desplegar en Render con Blueprint

1. Ve a https://dashboard.render.com
2. Haz clic en **"New +"** → **"Blueprint"**
3. Conecta tu repositorio `restaurante-admin`
4. Render detectará el archivo `render.yaml` automáticamente
5. Haz clic en **"Apply"**

Render creará automáticamente:
- Base de datos PostgreSQL
- Backend (API FastAPI)
- Frontend (React estático)

El proceso tarda **5-10 minutos** la primera vez.

---

## Paso 3 — Configurar la URL del backend en el frontend

Después del primer deploy, necesitas una configuración manual (solo una vez):

1. En el dashboard de Render, ve al servicio **restaurante-backend**
2. Copia la URL que aparece arriba, tiene este formato:
   `https://restaurante-backend.onrender.com`
3. Ve al servicio **restaurante-frontend**
4. Clic en **"Environment"**
5. Edita la variable `VITE_API_URL` y pega la URL del backend
6. Haz clic en **"Save Changes"** → el frontend se redeploya automáticamente

---

## Paso 4 — Acceder al sistema

- **Frontend:** `https://restaurante-frontend.onrender.com`
- **Backend API Docs:** `https://restaurante-backend.onrender.com/docs`

**Credenciales iniciales:**
- Email: `admin@restaurante.com`
- Contraseña: `admin123`

> ⚠️ Cambia la contraseña del admin después del primer login en Admin → Usuarios

---

## Notas importantes sobre el plan gratuito de Render

- Los servicios gratuitos se "duermen" después de 15 minutos de inactividad
- El primer request después del sueño tarda ~30 segundos en despertar
- Para uso en producción real, el plan **Starter ($7/mes)** evita esto

---

## Actualizaciones futuras

Cada vez que hagas cambios al código:

```bash
git add .
git commit -m "descripción del cambio"
git push
```

Render detecta el push y redespliega automáticamente.
