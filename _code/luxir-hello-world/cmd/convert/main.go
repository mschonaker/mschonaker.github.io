package main

// convert turns the Algolia ecommerce dataset (one JSON array) into the
// NDJSON that Luxir ingests, renaming fields to the schemaless templates.

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
)

type input struct {
	ObjectID       string   `json:"objectID"`
	Name           string   `json:"name"`
	ShortDesc      string   `json:"shortDescription"`
	Manufacturer   string   `json:"manufacturer"`
	Categories     []string `json:"categories"`
	SalePrice      float64  `json:"salePrice"`
	CustomerReview int      `json:"customerReviewCount"`
	Thumbnail      string   `json:"thumbnailImage"`
}

func main() {
	f, err := os.Open(os.Args[1])
	if err != nil {
		panic(err)
	}
	defer f.Close()
	raw, err := io.ReadAll(f)
	if err != nil {
		panic(err)
	}
	var items []input
	if err := json.Unmarshal(raw, &items); err != nil {
		panic(err)
	}
	enc := json.NewEncoder(os.Stdout)
	for _, d := range items {
		cats := d.Categories[:0:0]
		for _, c := range d.Categories {
			if c != "" {
				cats = append(cats, c)
			}
		}
		doc := map[string]any{
			"id":      d.ObjectID,
			"title_t": d.Name,
		}
		if d.ShortDesc != "" {
			doc["description_t"] = d.ShortDesc
		}
		if d.Manufacturer != "" {
			doc["brand_name"] = d.Manufacturer
		}
		if len(cats) > 0 {
			doc["category_names"] = cats
		}
		if d.SalePrice > 0 {
			doc["price_f"] = d.SalePrice
		}
		if d.CustomerReview > 0 {
			doc["reviews_i"] = d.CustomerReview
		}
		if d.Thumbnail != "" {
			doc["image_s"] = d.Thumbnail
		}
		if err := enc.Encode(doc); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	}
}
