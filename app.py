import streamlit as st
import os
import json
import pandas as pd
from shapely.geometry import Polygon
import geopandas as gpd
from datetime import datetime
from streamlit.components.v1 import html

st.set_page_config(page_title="Cartographie des Parcelles", layout="wide")

if os.path.exists("style.css"):
    with open("style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

DOSSIER_SAUVEGARDE = "donnees_champs"
os.makedirs(DOSSIER_SAUVEGARDE, exist_ok=True)

st.title("📍 Numérisation des Placettes PROMUVER-SL")

# Initialisation dataframe des espèces dans la session
if "df_especes" not in st.session_state:
    st.session_state.df_especes = pd.DataFrame(columns=["Nom scientifique", "Nombre de pieds"])

# -------- FORMULAIRE PRINCIPAL --------
st.subheader("Informations de la parcelle")

with st.form("formulaire_parcelle"):
    code_parcelle = st.text_input("Code de la parcelle")
    proprietaire = st.text_input("Nom du propriétaire")
    region = st.text_input("Région")
    commune = st.text_input("Commune")
    remarques = st.text_area("Remarques")

    st.markdown("### Inventaire des espèces présentes")
    df_edit = st.data_editor(
        st.session_state.df_especes,
        num_rows="dynamic",
        use_container_width=True,
        key="data_editor_especes"
    )

    submitted = st.form_submit_button("Valider le formulaire")

    if submitted:
        # Conversion sécurisée de la colonne Nombre de pieds en int
        df_edit["Nombre de pieds"] = pd.to_numeric(df_edit["Nombre de pieds"], errors="coerce")

        if not code_parcelle.strip() or not proprietaire.strip() or not commune.strip():
            st.warning("Merci de remplir tous les champs obligatoires.")
        elif df_edit.empty or df_edit["Nom scientifique"].str.strip().eq("").all() or (df_edit["Nombre de pieds"].fillna(0) <= 0).all():
            st.warning("Merci d'ajouter au moins une espèce avec un nombre de pieds > 0.")
        else:
            # Nettoyage des données valides
            df_valid = df_edit.dropna(subset=["Nom scientifique", "Nombre de pieds"])
            df_valid = df_valid[df_valid["Nom scientifique"].str.strip() != ""]
            df_valid = df_valid[df_valid["Nombre de pieds"] > 0]
            st.session_state.df_especes = df_valid.reset_index(drop=True)
            st.session_state["formulaire_valide"] = True
            st.success("✅ Formulaire validé. Passez à la cartographie.")

# -------- CARTE --------
if st.session_state.get("formulaire_valide", False):
    st.subheader("🗺️ Délimitation de la parcelle sur le terrain")

    html_code = """
    <html>
    <head>
      <meta charset="utf-8" />
      <title>Carte Parcelle</title>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
      <style>
        #map { height: 600px; }
        button { margin-top: 10px; padding: 6px 12px; font-weight: bold; background-color: #1abc9c; color: white; border: none; border-radius: 6px; cursor: pointer; }
        button:hover { background-color: #148f77; }
      </style>
    </head>
    <body>
      <div id="map"></div>
      <button onclick="fermerPolygone()">✅ Fermer le polygone</button>

      <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
      <script>
        var map = L.map('map').fitWorld();

        L.tileLayer('https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}', {
          maxZoom: 20,
          subdomains:['mt0','mt1','mt2','mt3'],
          attribution: "Google Satellite"
        }).addTo(map);

        var userMarker = null;
        var polygonPoints = [];
        var polyline = null;
        var polygon = null;

        function onLocationFound(e) {
          if (!userMarker) {
            userMarker = L.marker(e.latlng).addTo(map);
          } else {
            userMarker.setLatLng(e.latlng);
          }
          if (!document.getElementById("addPointBtn")) {
            var btn = document.createElement("button");
            btn.id = "addPointBtn";
            btn.innerHTML = "📍 Ajouter ce point";
            btn.onclick = function() {
              polygonPoints.push([e.latlng.lat, e.latlng.lng]);
              if (polyline) {
                map.removeLayer(polyline);
              }
              polyline = L.polyline(polygonPoints, {color: 'blue'}).addTo(map);
            };
            document.body.appendChild(btn);
          }
        }

        function onLocationError(e) {
          alert("Erreur GPS : " + e.message);
        }

        function fermerPolygone() {
          if (polygonPoints.length < 3) {
            alert("Il faut au moins 3 points.");
            return;
          }
          if (polygon) {
            map.removeLayer(polygon);
          }
          polygon = L.polygon(polygonPoints, {color: 'green'}).addTo(map);

          // Stocker temporairement les points dans le titre de la page (hack simple)
          document.title = JSON.stringify(polygonPoints);
          alert("Polygone fermé. Copiez les coordonnées du polygone depuis la console navigateur.");
        }

        map.on('locationfound', onLocationFound);
        map.on('locationerror', onLocationError);

        map.locate({setView: true, maxZoom: 18, watch: true});
      </script>
    </body>
    </html>
    """

    html_component = html(html_code, height=700)

    coords_input = st.text_area("Collez ici les coordonnées du polygone (format JSON)", height=150)

    if coords_input:
        try:
            points = json.loads(coords_input)
            if len(points) >= 3:
                poly = Polygon([(lon, lat) for lat, lon in points])  # inversion lat-lon en lon-lat
                gdf = gpd.GeoDataFrame([{
                    "code_parcelle": code_parcelle,
                    "proprietaire": proprietaire,
                    "region": region,
                    "commune": commune,
                    "especes": json.dumps(st.session_state.df_especes.to_dict(orient="records"), ensure_ascii=False),
                    "remarques": remarques,
                }], geometry=[poly], crs="EPSG:4326")
                gdf = gdf.to_crs(epsg=3857)
                surface_m2 = gdf.geometry.area.values[0]
                surface_ha = surface_m2 / 10000
                gdf["surface_ha"] = surface_ha
                gdf = gdf.to_crs(epsg=4326)

                if st.button("📥 Enregistrer le polygone et données"):
                    nom_fichier = f"{code_parcelle}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.geojson"
                    chemin = os.path.join(DOSSIER_SAUVEGARDE, nom_fichier)
                    gdf.to_file(chemin, driver="GeoJSON")
                    st.success(f"✅ Polygone et données enregistrés sous {nom_fichier}")

                st.write(f"Surface approximative: **{surface_ha:.3f} ha**")
            else:
                st.warning("Le polygone doit avoir au moins 3 points.")
        except Exception as e:
            st.error(f"Erreur lors du traitement des coordonnées : {e}")

else:
    st.info("Veuillez remplir et valider le formulaire pour accéder à la cartographie.")

st.markdown(
    """
    <style>
    .footer {
        position: fixed;
        bottom: 10px;
        width: 100%;
        text-align: center;
        font-size: 12px;
        color: gray;
    }
    </style>
    <div class="footer">Développé par <b>Moussa Diédhiou</b></div>
    """,
    unsafe_allow_html=True,
)