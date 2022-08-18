from iiif_prezi.factory import ManifestFactory

fac = ManifestFactory()
# Where the resources live on the web
fac.set_base_prezi_uri("http://localhost:8081/2005-0025/")

# Default Image API information
fac.set_base_image_uri("http://localhost:8182/iiif/2/")
fac.set_iiif_image_info(2.0, 2)

manifest = fac.manifest(label={"nl": "Holiday"})

manifest.set_metadata(
    {
        "label": {"nl": "Locatie", "en": "Location"},
        "value": {
            "nl": "51°3'20.9\"N, 3°43'12.4\"E",
            "en": "51°3'20.9\"N, 3°43'12.4\"E",
        },
    }
)

manifest.set_metadata(
    {"label": {"nl": "Gebeurtenis.tijd"}, "value": {"nl": "undefined/1972~"}}
)
manifest.set_metadata(
    {"label": {"nl": "Entiteit.type"}, "value": {"nl": "huishoudelijke apparaten (ok)"}}
)

manifest.set_metadata(
    {"label": {"nl": "Activiteit.uitgevoerdDoor"}, "value": {"nl": "Nova"}}
)

manifest.set_metadata(
    {"label": {"nl": "Gebeurtenis.plaats"}, "value": {"nl": "Tongeren"}}
)

manifest.seeAlso = {
    "@id": "https://stad.gent/id/mensgemaaktobject/dmg/530009722",
    "format": "application/json+ld",
}

manifest.description = {
    "nl": "Reisstrijkijzer van de Belgische producent Nova. Dit was het enige reisstrijkijzer dat Nova op de markt heeft gebracht. Het zwarte handvat kan ingeklapt worden om zo compact mee te nemen op reis. Het toestel heeft een zwarte draaischakelaar dat de temperatuur van de te strijken stof aangeeft, wat niet frequent voorkomt bij reisstrijkijzers. Het toestel wordt in de gebruiksaanwijzing aangeprezen voor zijn 'extra platte' vorm en weegt 660 gram. De originele productverpakking, tevens aanwezig, is vormgegeven als een reiskoffertje."
}
manifest.viewingDirection = "top-to-bottom"

seq = manifest.sequence()

cvs1 = seq.canvas(ident="2005-0025_1.JPG", label="Strijkijzer")
cvs1.set_image_annotation("2005-0025_1.JPG", iiif=True)

cvs2 = seq.canvas(ident="2005-0025_2.JPG", label="Strijkijzer opgeplooid")
cvs2.set_image_annotation("2005-0025_2.JPG", iiif=True)

cvs3 = seq.canvas(ident="2005-0025_3.JPG", label="Doos")
cvs3.set_image_annotation("2005-0025_3.JPG", iiif=True)

data = manifest.toString(compact=False)
print(data)
