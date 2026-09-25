"""Catálogo Nacional de Oficios y Habilidades de Colombia (CUOC / SENA).

Fuente: "lista de oficios y habilidades.md" (categorías y habilidades ampliadas)
+ "módulo de oficios y habilidades.md" (rutas certificables).

Cada OFICIO (categoría = grupo del catálogo) trae sus COMPETENCIAS ampliadas
y una ruta certificable de 2 niveles: Quiz (>=80%) + Certificación de estudios.

Formato: (categoria, nombre, descripcion, [competencias], [preguntas del quiz])
"""

# Categorías del catálogo (orden de visualización)
CATEGORIAS = [
    ("construccion", "Construcción, Obra Blanca, Mampostería y Estructuras"),
    ("climatizacion", "Climatización, Electrodomésticos y Tecnología"),
    ("domesticos", "Servicios Domésticos, Cuidado y Logística Urbana"),
    ("estetica", "Estética, Belleza y Cuidado Personal"),
    ("mecanica", "Servicios Mecánicos y Automotrices (Móviles)"),
]

CATALOGO_OFICIOS = [
    # ── 1. Construcción, Obra Blanca, Mampostería y Estructuras ──
    ("construccion", "Plomería y Fontanería",
     "Instalación y reparación de tuberías, grifería, sanitarios y sistemas hidrosanitarios.",
     [
         "Termofusión de tuberías (PVC, CPVC, PPR)",
         "Detección y reparación de fugas en muros, placas y acometidas",
         "Instalación, mantenimiento y reparación de sanitarios, lavamanos y grifería",
         "Mantenimiento e instalación de motobombas, tanques elevados e hidroflo",
         "Sondeo y destape técnico de cañerías, bajantes y trampas de grasa",
         "Instalación de calentadores de agua (gas y eléctricos)",
     ],
     [
         {"pregunta": "¿Qué herramienta se usa para sellar roscas de tubería?",
          "opciones": ["Teflón", "Alicate universal", "Nivel de burbuja", "Martillo"], "correcta": 0},
         {"pregunta": "¿Qué material se usa para unir tubería PPR?",
          "opciones": ["Termofusión", "Silicón", "Cinta de teflón", "Resina epóxica"], "correcta": 0},
         {"pregunta": "La causa más común de fuga en un sifón es:",
          "opciones": ["Empaque desgastado", "Presión excesiva", "Tubería de cobre", "Válvula cerrada"], "correcta": 0},
     ]),
    ("construccion", "Electricidad Residencial y Comercial",
     "Instalación de cableado, tableros, iluminación y mantenimiento eléctrico residencial y comercial.",
     [
         "Trazado y tendido de cableado estructurado y ductos (tubo conduit/PVC)",
         "Instalación de tableros eléctricos, breakers y balanceo de cargas",
         "Montaje de iluminación LED, lámparas, apliques y redes de tomacorrientes/interruptores",
         "Diagnóstico, rastreo de cortocircuitos y corrección de sobrecargas",
         "Instalación y puesta a tierra (varillas copperweld y tableros)",
         "Conexión de acometidas monofásicas, bifásicas y trifásicas",
     ],
     [
         {"pregunta": "¿Qué norma exige el uso de breakers en tableros residenciales?",
          "opciones": ["RETIE", "NTC 2050", "Ambas", "Ninguna"], "correcta": 2},
         {"pregunta": "Antes de manipular un circuito se debe:",
          "opciones": ["Cortar el breaker y verificar ausencia de tensión", "Trabajar con tensión si es rápido",
                       "Usar guantes de tela", "Conectar a tierra las manos"], "correcta": 0},
     ]),
    ("construccion", "Albañilería, Mampostería y Cimentación",
     "Obra gris, mampostería, enchapes, nivelación y cimentaciones menores.",
     [
         "Pegado de ladrillo, bloque de concreto, estructural y pañete/revoque de muros",
         "Enchape y pegado de cerámica, porcelanato, mármol y tabletas",
         "Nivelación, afinado de pisos y vaciado de contrapisos",
         "Preparación de mezclas, morteros y concretos con dosificación según norma",
         "Fundición de vorigas, columnas, cimientos menores y placas",
         "Demolición de muros no estructurales y retiro de escombros",
     ],
     [
         {"pregunta": "La proporción típica de un mortero de pega es:",
          "opciones": ["1:3", "1:10", "1:20", "2:2"], "correcta": 0},
         {"pregunta": "Antes de enchapar se debe:",
          "opciones": ["Humedecer y nivelar la superficie", "Pintar el muro", "Colocar teflón", "Nada"], "correcta": 0},
     ]),
    ("construccion", "Pintura, Impermeabilización y Acabados",
     "Pintura de interiores, exteriores, impermeabilización y acabados decorativos.",
     [
         "Aplicación de pintura tipo 1, 2 y 3 (vinilo, esmalte, epóxica)",
         "Estucado tradicional, plástico y aplicación de veneciano/graniplast",
         "Resane de humedad, salitre, hongo y fisuras en muros/techos",
         "Impermeabilización de terrazas, cubiertas, placas y jardineras (manta asfáltica/líquida)",
         "Manejo de equipo de compresión y pistola de aire (Airless)",
         "Pintura de fachadas en altura y aplicación de masillas protectoras",
     ],
     [
         {"pregunta": "Antes de pintar una pared con humedad se debe:",
          "opciones": ["Tratar la humedad y aplicar sellador", "Pintar directo con vinilo",
                       "Lijar en seco y pintar", "Ninguna de las anteriores"], "correcta": 0},
         {"pregunta": "El estuco plástico se aplica para:",
          "opciones": ["Alisar la superficie", "Impermeabilizar", "Matar hongos", "Adherir pintura"], "correcta": 0},
     ]),
    ("construccion", "Drywall",
     "Instalación de placas de yeso laminado, cielos rasos y aislamiento.",
     [
         "Instalación de estructura metálica (perfilería, omegas, parales y calibres)",
         "Montaje y atornillado de placas de yeso (Drywall) y fibrocemento (Superboard)",
         "Encintado, masillado y lijado de juntas de acabado invisible",
         "Instalación de cielos rasos en PVC, icopor, fibra de vidrio y drywall",
         "Aislamiento termoacústico con lana de roca o fibra de vidrio",
     ],
     [
         {"pregunta": "La perfilería metálica del drywall se instala con:",
          "opciones": ["Tornillos y remaches", "Silicón", "Clavos de acero", "Pegamento"], "correcta": 0},
     ]),
    ("construccion", "Carpintería en Madera, MDF y RH (Mueble Fijo y RTA)",
     "Fabricación e instalación de muebles, estructuras y acabados en madera y MDF.",
     [
         "Ensamble y armado de muebles RTA (muebles en caja de aglomerado/MDF/MDP)",
         "Fabricación y reparación de cocinas integrales, closets y cajoneras",
         "Mantenimiento y cambio de bisagras de parche, rieles telescópicos y pistones",
         "Cepillado, pulido, entintado y restauración de madera maciza",
         "Aplicación de selladores, lacas, barnices y poliuretano",
         "Instalación de puertas de madera, marcos, jambas y zócalos/guardaluz",
     ],
     [
         {"pregunta": "¿Qué madera es más estable para muebles de interior?",
          "opciones": ["Pino seco", "Madera verde", "Aglomerado sin sellar", "Guadua"], "correcta": 0},
         {"pregunta": "¿Qué se usa para unir cajoneras de MDF?",
          "opciones": ["Espigas + cola blanca", "Clavos sueltos", "Silicón", "Cinta doble faz"], "correcta": 0},
     ]),
    ("construccion", "Soldadura, Metalmecánica y Carpintería Metálica",
     "Soldadura eléctrica, MIG/TIG, corte y fabricación de estructuras metálicas.",
     [
         "Soldadura eléctrica revestida (SMAW/Electrodo), MIG y TIG",
         "Corte, trazado y ensamble con pulidora, tronzadora y oxicorte",
         "Fabricación e instalación de rejas, portones, cerramientos y balcones",
         "Fabricación y montaje de estructuras metálicas livianas y cerchas",
         "Mantenimiento de pasamanos, escaleras e instalación de cubiertas en teja de zinc/policarbonato",
     ],
     [
         {"pregunta": "¿Qué elemento de protección es obligatorio al soldar?",
          "opciones": ["Careta con filtro", "Lentes de sol", "Guantes de tela", "Tapabocas"], "correcta": 0},
         {"pregunta": "El electrodo revestido se usa en soldadura:",
          "opciones": ["SMAW", "TIG", "MIG", "Láser"], "correcta": 0},
     ]),
    ("construccion", "Cerrajería",
     "Apertura técnica, instalación y mantenimiento de cerraduras y seguridad física.",
     [
         "Apertura técnica de cerraduras residenciales, comerciales y candados",
         "Cambio de guardas, cilindros, pestillos y duplicado de llaves",
         "Instalación de cerraduras de alta seguridad, cerrojos de incrustar y sobreponer",
         "Instalación y configuración de cerraduras digitales, biométricas y teclados de acceso",
         "Mantenimiento, ajuste y alineación de puertas blindadas y entambadas",
     ],
     [
         {"pregunta": "Para abrir una cerradura sin dañarla se usa:",
          "opciones": ["Técnica de ganzúa", "Martillo", "Taladro", "Palanca"], "correcta": 0},
     ]),

    # ── 2. Climatización, Electrodomésticos y Tecnología ──
    ("climatizacion", "Mantenimiento e Instalación de Aire Acondicionado y Climatización",
     "Instalación y mantenimiento de equipos de climatización (minisplit, multisplit).",
     [
         "Mantenimiento preventivo (lavado químico, desinfección de evaporadores y condensadores de minisplit/piso techo)",
         "Instalación y desinstalación técnica de equipos de aire acondicionado minisplit y multisplit",
         "Carga y recarga de gases refrigerantes (R410A, R22, R32) y prueba de estanqueidad con nitrógeno",
         "Detección y corrección de fugas en tuberías de cobre y aislamiento térmico",
         "Diagnóstico y reparación de fallas eléctricas en tarjetas electrónicas, capacitores y compresores",
     ],
     [
         {"pregunta": "El gas R410A se usa en equipos:",
          "opciones": ["Minisplit modernos", "Neveras antiguas", "Extintores", "Ninguno"], "correcta": 0},
     ]),
    ("climatizacion", "Reparación y Mantenimiento de Electrodomésticos",
     "Servicio técnico de lavadoras, neveras, estufas y pequeños electrodomésticos.",
     [
         "Servicio técnico y mantenimiento de lavadoras (carga frontal y superior) y secadoras a gas/eléctricas",
         "Reparación de refrigeradores, neveras, nevecones no-frost y congeladores (cambio de termostato, motor, gas)",
         "Diagnóstico y reparación de estufas a gas/eléctricas, hornos empotrados y cubiertas",
         "Mantenimiento y reparación de microondas, licuadoras industriales y pequeños electrodomésticos",
         "Cambio de rodamientos, retenes, arañas y componentes mecánicos de lavado",
     ],
     [
         {"pregunta": "Un no-frost que no enfría puede tener:",
          "opciones": ["Falla de deshielo", "Poca pintura", "Ruido del motor", "Ninguna"], "correcta": 0},
     ]),
    ("climatizacion", "Técnico en Redes, CCTV y Soporte Informático",
     "Cableado estructurado, redes Wi-Fi, videovigilancia y soporte informático.",
     [
         "Instalación, ponchado y certificación de cableado estructurado (UTP Cat 5e/6/6A, conectores RJ45)",
         "Configuración de routers, repetidores Wi-Fi, redes MESH y redes locales (LAN)",
         "Instalación y configuración de sistemas de videovigilancia (CCTV analógico e IP) y alarmas de seguridad",
         "Mantenimiento preventivo y correctivo de computadores de escritorio, portátiles y limpieza física",
         "Formateo, instalación de sistemas operativos, drivers, antivirus y eliminación de malware",
         "Ensamblaje, optimización de hardware (cambio de SSD/RAM) y recuperación de datos",
     ],
     [
         {"pregunta": "El conector de un cable UTP es:",
          "opciones": ["RJ45", "RJ11", "USB-C", "BNC"], "correcta": 0},
     ]),

    # ── 3. Servicios Domésticos, Cuidado y Logística Urbana ──
    ("domesticos", "Jardinería, Paisajismo y Zonas Verdes",
     "Poda, mantenimiento de zonas verdes, abono y paisajismo básico.",
     [
         "Poda de formación, despeje y mantenimiento de árboles, arbustos y setos",
         "Manejo de guadañadora, cortacésped, cortasetos y herramientas de jardinería",
         "Abono, fertilización y acondicionamiento químico/orgánico de tierras",
         "Identificación y control orgánico/químico de plagas y maleza",
         "Instalación de césped en rollo, plantas ornamentales y sistemas de riego manual/goteo",
     ],
     [
         {"pregunta": "¿En qué época se recomienda podar especies de floración temprana?",
          "opciones": ["Después de florecer", "Antes de florecer", "En cualquier época", "Nunca"], "correcta": 0},
     ]),
    ("domesticos", "Aseo, Limpieza General y Mantenimiento de Espacios",
     "Limpieza profunda, desinfección e higienización de espacios y muebles.",
     [
         "Limpieza profunda y desinfección de cocinas, estufas, campanas extractor e higienización de baños",
         "Lavado, desmanchado y planchado de prendas de vestir y lencería del hogar",
         "Lavado e higienización de muebles, sofás, colchones y alfombras con máquinas de inyección-extracción",
         "Limpieza técnica de vidrios, ventanales, marquesinas y espejos",
         "Organización integral de espacios interiores (closets, alacenas, depósitos)",
     ],
     [
         {"pregunta": "Para higienizar un colchón se usa:",
          "opciones": ["Máquina de inyección-extracción", "Escoba", "Agua con cloro directo", "Aspiradora de mano"], "correcta": 0},
     ]),
    ("domesticos", "Cuidado de Personas y Auxiliar Doméstico",
     "Auxiliar doméstico: cuidado de adultos mayores, niños y personas con movilidad reducida.",
     [
         "Acompañamiento, asistencia diaria y movilidad de adultos mayores o personas con movilidad reducida",
         "Cuidado de primera infancia y niños (niñera/babysitter) con enfoque recreativo/educativo",
         "Administración de medicamentos bajo prescripción médica y control de planillas",
         "Toma de signos vitales básicos (presión arterial, glucometría, saturación de oxígeno)",
         "Preparación de dietas especiales, alimentos balanceados y aseo del paciente",
     ],
     [
         {"pregunta": "Los medicamentos se administran:",
          "opciones": ["Bajo prescripción médica", "Libremente", "Solo de noche", "Nunca"], "correcta": 0},
     ]),
    ("domesticos", "Mudanzas, Acarreos y Manejo de Carga Liviana",
     "Embalaje, carga, transporte y montaje de enseres y mercancías.",
     [
         "Embalaje, empaque y rotulado de enseres con cartón, vinipel y plástico burbuja",
         "Carga, descarga y manipulación segura de muebles pesados y electrodomésticos",
         "Amarre, estiba y aseguramiento de carga en camiones o camionetas de estacas/furgones",
         "Desmonte y posterior armado de camas, comedores, bases y muebles modulares",
         "Transporte urbano de mercancías, encomiendas y acarreos express",
     ],
     [
         {"pregunta": "Los enseres frágiles se protegen con:",
          "opciones": ["Plástico burbuja", "Papel periódico", "Cinta de enmascarar", "Nada"], "correcta": 0},
     ]),

    # ── 4. Estética, Belleza y Cuidado Personal ──
    ("estetica", "Barbería, Peluquería y Estilismo",
     "Cortes, arreglo de barba, colorimetría y tratamientos capilares.",
     [
         "Cortes masculinos clásicos y modernos (Fades, degradados, rasurados)",
         "Arreglo, perfilado, hidratación y tinte de barba",
         "Corte femenino, cepillado, planchado y peinados de ocasión",
         "Colorimetría capilar: tinturas, mechas, balayage, decoloración y cubrimiento de canas",
         "Tratamientos de restauración capilar (queratinas, repolarización, aminoplástia, cirugía capilar)",
     ],
     [
         {"pregunta": "El Fade es un tipo de corte:",
          "opciones": ["Masculino degradado", "Femenino", "Infantil", "Ninguno"], "correcta": 0},
     ]),
    ("estetica", "Manicura, Pedicura y Estética de Uñas",
     "Manicura, pedicura, esmaltado semipermanente y escultura de uñas.",
     [
         "Manicura y pedicura tradicional, Rusa y mixta",
         "Esmaltado semipermanente y retiro adecuado del producto",
         "Esculpido y montaje de uñas en acrílico, gel, polygel y prensa (Soft Gel)",
         "Diseño a mano alzada, Nail Art, encapsulados y pedrería",
         "Pedicura profunda, tratamiento de durezas y exfoliación",
     ],
     [
         {"pregunta": "El acrílico y el gel se usan para:",
          "opciones": ["Esculpir uñas", "Pintar paredes", "Diseñar cejas", "Ninguno"], "correcta": 0},
     ]),
    ("estetica", "Estética Facial y Corporal (No Invasiva)",
     "Limpieza facial, depilación, cejas, pestañas y masajes (no invasiva).",
     [
         "Limpieza facial profunda, extracción de comedones y alta frecuencia",
         "Depilación corporal y facial (con cera, hilo, crema o pinza)",
         "Diseño, pigmentación (Henna), laminado de cejas y elevación de pestañas (Lifting/Rizado)",
         "Colocación y retoque de extensiones de pestañas (pelo a pelo, volumen ruso)",
         "Masajes relajantes, descontracturantes y drenaje linfático manual",
     ],
     [
         {"pregunta": "La extracción de comedones requiere:",
          "opciones": ["Material esterilizado", "Uñas largas", "Presión excesiva", "Nada"], "correcta": 0},
     ]),

    # ── 5. Servicios Mecánicos y Automotrices (Móviles) ──
    ("mecanica", "Mecánica Rápida de Automóviles",
     "Mantenimiento básico de automóviles: aceite, frenos, diagnóstico y batería.",
     [
         "Cambio de aceite, filtro de motor, filtro de aire y de combustible",
         "Revisión, mantenimiento y cambio de pastillas y discos de freno",
         "Diagnóstico computarizado por escáner OBD2 y lectura de códigos de error",
         "Cambio de batería, iniciación de corriente y revisión del sistema de carga (alternador)",
         "Reparación e instalación de correas de accesorio, mangueras y fuga de refrigerante",
     ],
     [
         {"pregunta": "El escáner OBD2 se usa para:",
          "opciones": ["Leer códigos de error", "Cambiar aceite", "Pintar", "Nivelar frenos"], "correcta": 0},
     ]),
    ("mecanica", "Mecánica y Mantenimiento de Motocicletas",
     "Mantenimiento y reparación de motocicletas: motor, arrastre, llantas y frenos.",
     [
         "Sincronización de motor, limpieza de carburador o cuerpo de aceleración (Inyección Electrónica)",
         "Cambio de kit de arrastre (piñón, catalina y cadena) y tensionado",
         "Reparación y parchado de llantas (despinchado), montaje de neumáticos y sello neumático",
         "Mantenimiento de frenos de disco y tambor, cambio de guayas de acelerador/clutch",
         "Mantenimiento del sistema eléctrico (luces, direccionales, pito, encendido eléctrico)",
     ],
     [
         {"pregunta": "El kit de arrastre incluye:",
          "opciones": ["Piñón, catalina y cadena", "Aceite y filtro", "Frenos y disco", "Batería"], "correcta": 0},
     ]),
]


def build_niveles(quiz_preguntas):
    """Ruta certificable del oficio: Quiz (>=80%) + Certificación de estudios."""
    return [
        {"nombre": "Básico", "tipo": "quiz", "quiz": quiz_preguntas},
        {"nombre": "Certificado técnico", "tipo": "certificacion"},
    ]