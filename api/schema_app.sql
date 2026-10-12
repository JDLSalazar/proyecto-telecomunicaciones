-- =====================================================================
-- schema_app.sql: tablas PROPIAS de la aplicación (no son de FreeRADIUS)
-- Las líneas que empiezan con "--" son comentarios: SQL las ignora.
-- =====================================================================

-- Tabla de CLIENTES registrados en la tienda.
CREATE TABLE app_users (
  id INT AUTO_INCREMENT PRIMARY KEY,         -- número único de cada cliente (1, 2, 3...), se asigna solo
  username VARCHAR(64) UNIQUE NOT NULL,      -- usuario para iniciar sesión. UNIQUE = no se puede repetir
  email VARCHAR(120) NOT NULL,               -- correo (obligatorio: NOT NULL)
  phone VARCHAR(20),                         -- teléfono (opcional, puede quedar vacío)
  password_hash VARCHAR(255) NOT NULL,       -- la contraseña CIFRADA (hash), nunca la real
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP);  -- fecha de registro, se llena sola

-- Tabla de PAGOS: cada intento de pago queda registrado (aprobado o fallido).
CREATE TABLE app_payments (
  id INT AUTO_INCREMENT PRIMARY KEY,         -- número único del pago
  username VARCHAR(64) NOT NULL,             -- quién pagó
  plan VARCHAR(20) NOT NULL,                 -- qué plan compró: "1h", "1d" o "7d"
  amount DECIMAL(8,2) NOT NULL,              -- monto en quetzales, con 2 decimales (ej. 15.00)
  status VARCHAR(20) NOT NULL,               -- "approved" (aprobado) o "failed" (fallido)
  card_last4 CHAR(4),                        -- SOLO los últimos 4 dígitos de la tarjeta (seguridad)
  reference VARCHAR(40),                     -- código de referencia del pago (como un número de recibo)
  error_code VARCHAR(30),                    -- motivo del rechazo, si falló (ej. "DECLINED")
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP);  -- fecha y hora del intento
