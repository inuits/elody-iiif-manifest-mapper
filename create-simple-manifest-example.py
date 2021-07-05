from iiif_prezi.factory import ManifestFactory

fac = ManifestFactory()
# Where the resources live on the web
fac.set_base_prezi_uri("http://localhost:8081/2017-0452/")

# Default Image API information
fac.set_base_image_uri("http://localhost:8182/iiif/2/")
fac.set_iiif_image_info(2.0, 2)

manifest = fac.manifest(label={"nl": "Doorzichtig waterreservoir"})

manifest.set_metadata(
    {'label' : {'nl':'Locatie', 'en':'Location'}, 
     'value': {'nl': '51°3\'20.9"N, 3°43\'12.4"E', 'en': '51°3\'20.9"N, 3°43\'12.4"E'}
    })

manifest.set_metadata(
    {'label' : {'nl':'Gebeurtenis.tijd'}, 
     'value': {'nl': '1997~'}
    })
manifest.set_metadata(
    {'label' : {'nl':'Entiteit.type'}, 
     'value': {'nl': 'huishoudelijke apparaten (ok)'}
    })

manifest.set_metadata(
    {'label' : {'nl':'Activiteit.uitgevoerdDoor'}, 
     'value': {'nl': 'Nova'}
    })

manifest.set_metadata(
    {'label' : {'nl':'Gebeurtenis.plaats'}, 
     'value': {'nl': 'Tongeren'}
    })

manifest.seeAslo = {"@id": "https://stad.gent/id/mensgemaaktobject/dmg/530026423", "format": "application/json+ld"}

manifest.description = {"nl": "Doorzichtig plastic reservoir met aanduiding van maateenheden in stift. Binnenin bevinden zich diverse onderdelen. Dit is een prototype van de geurfilter van een geurloze fiteuse die door Nova ontwikkeld werd op het einde van hun productie."}
#manifest.viewingDirection = "left-to-right"

seq = manifest.sequence() 

cvs = seq.canvas(ident="2017-0452_1.JPG", label="2017-0452")
cvs.set_image_annotation("2017-0452_1.JPG", iiif=True)

data = manifest.toString(compact=False)
print(data)
