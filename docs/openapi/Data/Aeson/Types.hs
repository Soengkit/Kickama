module Data.Aeson.Types
  ( Parser
  , parseMaybe
  ) where

type Parser = Either String

parseMaybe :: (a -> Parser b) -> a -> Maybe b
parseMaybe parser value =
  case parser value of
    Right result -> Just result
    Left _ -> Nothing
