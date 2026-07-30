import pathlib
import warnings
import rdflib
import prov.model  # type: ignore
import prov.dot  # type: ignore
import charmonium.time_block


def swallow_warnings() -> list[warnings.WarningMessage]:
    with warnings.catch_warnings(record=True) as caught:  # caught: List[WarningMessage]
        warnings.simplefilter("always")
        # ... run code that may emit warnings ...
        # e.g., warnings.warn("do not show message", UserWarning)
        return caught

PROV = rdflib.namespace.PROV
RDF = rdflib.namespace.RDF
RDFS = rdflib.namespace.RDFS
PROV_LABEL = rdflib.URIRef("http://www.w3.org/ns/prov#label")
AD_HOC_NAMESPACE = rdflib.Namespace("http://example.org/to-be-formalized/#")


def slice(graph: rdflib.Graph) -> rdflib.Graph:
    for triple in graph.triples((None, PROV_LABEL, None)):
        graph.remove(triple)
    return graph


def validate_prov(graph: rdflib.Graph) -> prov.model.ProvDocument:
    for subject, label in graph.subject_objects(RDFS.label):
        graph.add((subject, PROV_LABEL, label))

    graph_serialized = graph.serialize(format="turtle")
    
    with warnings.catch_warnings(record=True) as caught:
        prov_document = prov.model.ProvDocument.deserialize(
            content=graph_serialized,
            format="rdf",
            rdf_format="turtle",
        )
    print([wm.category.__name__ for wm in caught])

    for triple in graph.triples((None, PROV_LABEL, None)):
        graph.remove(triple)

    return prov_document


if __name__ == "__main__":
    import typer
    app = typer.Typer()
    @app.command()
    def main(
            input_provenance_ttl: pathlib.Path = pathlib.Path("provenance.ttl"),
            input_provenance_graph: pathlib.Path = pathlib.Path("provenance.dot"),
            output_provenance_ttl: pathlib.Path = pathlib.Path("provenance_sliced.ttl"),
            output_provenance_graph: pathlib.Path = pathlib.Path("provenance_sliced.dot"),
    ) -> None:
        rdf_graph = rdflib.Graph()
        rdf_graph.bind("rdf", RDF)
        rdf_graph.bind("ad_hoc", AD_HOC_NAMESPACE)
        with charmonium.time_block.ctx("Parse turtle"):
            rdf_graph.parse(input_provenance_ttl, format="turtle")
        with charmonium.time_block.ctx("Slice"):
            sliced_rdf_graph = slice(rdf_graph)
        with charmonium.time_block.ctx("Validate W3C PROV"):
            prov_document = validate_prov(sliced_rdf_graph)
        with charmonium.time_block.ctx("Serialize Turtle"):
            sliced_rdf_graph.serialize(str(output_provenance_ttl), format="turtle")
        with charmonium.time_block.ctx("Visualize"):
            prov_document_dot = prov.dot.prov_to_dot(prov_document, use_labels=True, show_nary=False, show_element_attributes=False, show_relation_attributes=False)
            prov_document_dot.write_raw(output_provenance_graph)
        print(f"{len(rdf_graph)} -> {len(sliced_rdf_graph)} triples")
        print(f"{len(list(rdf_graph.subjects(RDF.type, PROV.Activity)))} -> {len(list(sliced_rdf_graph.subjects(RDF.type, PROV.Activity)))} Activities")
        print(f"{len(list(rdf_graph.subjects(RDF.type, PROV.Entity)))} -> {len(list(sliced_rdf_graph.subjects(RDF.type, PROV.Entity)))} Entities")
        print(f"{input_provenance_ttl.stat().st_size // 1024}KiB -> {output_provenance_ttl.stat().st_size // 1024}KiB")
        print(f"{input_provenance_graph.stat().st_size // 1024}KiB -> {output_provenance_graph.stat().st_size // 1024}KiB")
    main()
