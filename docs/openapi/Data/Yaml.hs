module Data.Yaml
  ( ParseException(..)
  , decodeFileEither
  ) where

import Data.Aeson (FromJSON)

newtype ParseException = ParseException String
  deriving (Show, Eq)

decodeFileEither :: FromJSON a => FilePath -> IO (Either ParseException a)
decodeFileEither _ =
  pure (Left (ParseException "YAML decoding is unavailable in the OpenAPI build stub"))
