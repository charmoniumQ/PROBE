#lang at-exp racket/base

(require csv-reading)
(require racket/list)
(require racket/string)
(require (only-in txexpr txexpr txexpr* get-elements get-attrs))
(require "tags.rkt")

@doc{
  @style|{
    @page {
      size: 44in 34in;
      margin: 3cm;
    }
    * {
      font-family: sans-serif;
    }
    h1 {
      font-weight: normal;
      text-align: center;
      font-size: 1.0in;
      margin-bottom: 0in;
    }
    h2 {
      font-weight: normal;
      font-size: 0.75in;
    }
    p, li, table {
      font-size: 0.5in;
    }
    .row {
      display: flex;
      /*display: grid;*/
      /*grid-template-columns: 50% 50%;*/
    }
    .column {
      flex: 50%;
      margin-left: 4%;
      margin-right: 4%;
    }
    .container {
      width: 44in;
      height: 34in;
      /*background-color: lightblue;*/
      overflow: scroll;
    }
    .performance th {
      background-color: lightgray;
    }
    .performance {
      font-size: 0.3in;
    }
    .features td[data-content="yes"] {
      background-color: lightgreen;
    }
    .features td[data-content="no"] {
      background-color: salmon;
    }
    .features th {
      background-color: lightgray;
    }
    .features td {
      background-color: lightgray;
    }
    table {
      margin-left: auto;
      margin-right: auto;
    }
    img.center {
      margin-left: auto;
      margin-right: auto;
      display: block;
    }
    .byline {
      text-align: center;
      font-size: 0.6in;
    }
  }|
  @hsection["How to collect computational provenance"]{
    @div[#:class "row"]{
      @div[#:class "column"]{
        @hsection["What is provenance?"]{
          @p{The inputs (binaries, scripts, data) used to produce specific output}

          @p{Can be collected @emph{without} modifying programs}

          @figure[#:width "100%"]{
            @graphviz[#:width "17in" "example.dot"]
          }
        }
        @hsection["Why provenance?"]{
          @itemlist{
            @item{Reproducibility: what inputs do you need to run this program?}
            @item{Caching: when inputs are changed, what outputs are stale}
            @item{Comprehension: what version of the data did this output use}
          }
        }
        @hsection["Methods for collecting provenance"]{
          @(let* ([tab (llist->table "features" (csv->list (open-input-file "feature-table.csv")))]
                  [tab-attrs (get-attrs tab)]
                  [thead (first (get-elements tab))]
                  [tbody (second (get-elements tab))]
                  [tbody-rows (get-elements tbody)]
                  [tbody-rows*
                   (map
                     (lambda (row)
                       (txexpr
                         'tr
                         '()
                         (map
                           (lambda (cell) (txexpr 'td `((data-content ,(apply string-append (get-elements cell)))) (get-elements cell)))
                           (get-elements row))))
                     tbody-rows)])
            (txexpr* 'table tab-attrs thead (txexpr 'tbody '() tbody-rows*)))
        }
        @p{Ptrace is most studied, but LD_PRELOAD and eBPF are most compelling.}
        @hsection["Is it fast?"]{
          @figure[#:width "14in"]{
            @img[#:width "7in"]{log_overhead_hist.svg}
          }
          @p{Depends on the application!}
        }
      }
      @div[#:class "column"]{
        @hsection["How to make it faster?"]{
          @figure[#:width "13in"]{
            @img[#:width "12in"]{dendrogram.svg}
          }
          @figure[#:width "13in"]{
            @img[#:width "7in"]{clustering2.svg}
          }
          @(llist->table "performance" (csv->list (open-input-file "performance.csv")))
        }
        @hsection["What next?"]{
          @itemlist{
            @item{Record/replay (get reproducibility "for free")}
            @item{Differential debugging}
            @item{Make without Makefile}
            @item{How to eliminate redundancies?}
          }
        }
      }
    }
  }
}
