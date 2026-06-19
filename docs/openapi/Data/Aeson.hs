{-# LANGUAGE FlexibleInstances #-}
{-# LANGUAGE TypeSynonymInstances #-}

module Data.Aeson
  ( FromJSON(..)
  , ToJSON(..)
  , Value(..)
  , Object
  , encode
  , decode
  , object
  , withObject
  , (.=)
  , (.:?)
  , (.!=)
  ) where

import qualified Data.ByteString.Lazy as BL
import Data.Aeson.Types (Parser)
import qualified Data.Aeson.KeyMap as KM
import qualified Data.HashMap.Strict as HM
import Data.Text (Text)

type Object = KM.KeyMap Value

data Value
  = Object Object
  | String Text
  | Number Double
  | Bool Bool
  | Array [Value]
  | Null
  deriving (Show, Eq)

class FromJSON a where
  parseJSON :: Value -> Parser a
  parseJSON _ = Left "Data.Aeson stub does not decode values"

class ToJSON a where
  toJSON :: a -> Value
  toJSON _ = Null

encode :: ToJSON a => a -> BL.ByteString
encode _ = mempty

decode :: FromJSON a => BL.ByteString -> Maybe a
decode _ = Nothing

object :: [(Text, Value)] -> Value
object = Object . KM.fromList

withObject :: String -> (Object -> Parser a) -> Value -> Parser a
withObject _ parser (Object o) = parser o
withObject name _ _ = Left (name ++ ": expected object")

(.=) :: Text -> a -> (Text, Value)
name .= _ = (name, Null)

(.:?) :: FromJSON a => Object -> Text -> Parser (Maybe a)
objectValue .:? key =
  case KM.lookup key objectValue of
    Nothing -> pure Nothing
    Just value -> Just <$> parseJSON value

(.!=) :: Parser (Maybe a) -> a -> Parser a
parser .!= fallback = do
  value <- parser
  pure (maybe fallback id value)

instance FromJSON Value where
  parseJSON = pure

instance ToJSON Value where
  toJSON = id

instance FromJSON Text
instance FromJSON Bool
instance FromJSON Int
instance FromJSON Integer
instance FromJSON Double

instance FromJSON a => FromJSON [a]
instance FromJSON a => FromJSON (Maybe a)
instance (Ord k, FromJSON a) => FromJSON (HM.HashMap k a)

instance ToJSON Text
instance ToJSON Bool
instance ToJSON Int
instance ToJSON Integer
instance ToJSON Double
instance ToJSON a => ToJSON [a]
instance ToJSON a => ToJSON (Maybe a)
instance ToJSON a => ToJSON (HM.HashMap k a)
