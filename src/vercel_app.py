"""Point d'entrée de l'API sur Vercel (service « api » de vercel.json).

Vercel sert l'interface et l'API sous la même adresse : les requêtes /api/*
arrivent ici avec leur chemin complet, que les routes de l'API portent déjà.
Réglages par variables d'environnement du projet Vercel :

- EIT_DATABASE_URL : base Supabase, pooler en mode transaction (port 6543) ;
- EIT_ACCESS_CODE : code d'accès donné aux testeurs (fortement conseillé).

Seules des données fictives sont chargées dans une base hébergée.
"""

from eit_screening.api.app import create_app

app = create_app()
