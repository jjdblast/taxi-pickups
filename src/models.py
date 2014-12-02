#!/usr/bin/python
import sys
import operator
from abc import ABCMeta, abstractmethod
from sklearn import linear_model, svm, tree
import util
import numpy as np
from const import Const
from feature_extractor import FeatureExtractor


# Interface for our learning models.
class Model(object):
    __metaclass__ = ABCMeta

    @abstractmethod
    def train(self):
        '''
        Trains the learning model on the list of training examples provided in
        the dataset (passed in through the constructor).
        '''
        pass

    @abstractmethod
    def predict(self, test_example):
        '''
        Predicts the number of pickups for the test example provided.

        :param test_example: dict mapping feature names to feature values

        :return: Predicted number of pickups for the test example.
        '''
        pass

    @abstractmethod
    def __str__(self):
        pass

# This class can perform training and testing on the input regressor
# model. Specific model classes can subclass from `RegressionModel`.
class RegressionModel(Model):
    __metaclass__ = ABCMeta

    def __init__(self, database, dataset, regressor_model, sparse=True):
        self.db = database
        self.dataset = dataset
        self.table_name = Const.AGGREGATED_PICKUPS
        self.regressor = regressor_model

        # sparse determines whether data should be represented as sparse scipy
        # matrices as opposed to dense ones. (Some models such as the decision tree
        # regression model require a dense representation.)
        self.feature_extractor = FeatureExtractor(sparse)

    def train(self):
        '''
        See Model for comments on the parameters and return value.
        We are using `fit()` rather than `partial_fit()` since the January
        data is small enough to permit fitting all data into RAM.
        '''
        # Populate `row_dicts` with all training examples, represented as a
        # list of dicts.
        row_dicts = []
        while self.dataset.hasMoreTrainExamples():
            row_dicts.extend(self.dataset.getTrainExamples(Const.TRAIN_BATCH_SIZE))

        # Transform the training data into "vectorized" form.
        X = self.feature_extractor.getFeatureVectors(row_dicts)
        # Get the labels of the training examples.
        y = np.array([train_example['num_pickups'] for train_example in row_dicts])

        self.regressor.fit(X, y)

        if util.VERBOSE:
            self._printMemoryStats(row_dicts, X)
            self._printMostPredictiveFeatures(15)

    def predict(self, test_example):
        '''
        Predicts the number of pickups at the specified time and location,
        within a 1 hour interval and 0.01 x 0.01 degrees lat/long box.

        See Model for comments on the parameters and return value.
        '''
        vectorized_example = self.feature_extractor.getFeatureVectors([test_example], is_test=True)
        y = self.regressor.predict(vectorized_example)[0]
        y = max(0.0, y)
        return y

    def _printMemoryStats(self, row_dicts, X):
        print '\n\t---- Memory usage stats ----'
        print '\tTraining feature dicts: \t', sys.getsizeof(row_dicts), " bytes used"
        if hasattr(X.data, 'nbytes'):
            print '\tVectorized training data: \t', X.data.nbytes, " bytes used\n"
        else:
            print '\tVectorized training data: \t', sys.getsizeof(X), " bytes used\n"

    def _printMostPredictiveFeatures(self, n):
        """
        If the input model has feature coefficients, prints the n features whose
        coefficients are the highest, and the n features whose coefficients are
        the lowest.

        :param n: number of the best/worst features to print (prints 2n features total)
        """
        if not hasattr(self.regressor, 'coef_'):
            print '\tCannot print out the most predictive features for the model.'
            return

        feature_weights = []
        for feature_name, index in self.feature_extractor.getFeatureNameIndices().iteritems():
            feature_weights.append((feature_name, self.regressor.coef_[index]))
        feature_weights.sort(key=operator.itemgetter(1))

        def printFeatureWeight(feature_weight):
            print '\t%s:\t%f' % (feature_weight[0], feature_weight[1])

        print ('\tFeature\t\tWeight')
        [printFeatureWeight(feature_weight) for feature_weight in feature_weights[:n]]
        [printFeatureWeight(feature_weight) for feature_weight in feature_weights[-n:]]


class LinearRegression(RegressionModel):
    def __init__(self, database, dataset):
        sgd_regressor = linear_model.SGDRegressor(
            n_iter=1000, # Takes many iterations to converge.
            alpha=0.0, # Works better without regularization.
            learning_rate='invscaling',
            eta0=0.1, # Converges faster with higher-than-default initial learning rate.
            power_t=0.1,
            verbose=1 if util.VERBOSE else 0
        )
        RegressionModel.__init__(self, database, dataset, sgd_regressor)

    def __str__(self):
        return 'linear [linear regression model]'


class SupportVectorRegression(RegressionModel):
    def __init__(self, database, dataset):
        svr_regressor = svm.SVR(
            C=10000000.0, # With lower C values, the SVR underfits.
            verbose=util.VERBOSE
        )
        RegressionModel.__init__(self, database, dataset, svr_regressor)

    def __str__(self):
        return 'svr [support vector regression model]'

class DecisionTreeRegression(RegressionModel):
    def __init__(self, database, dataset):
        # NOTE: The decision tree is very sensitive to max_depth and
        # min_samples_leaf parameters. These can control the degree
        # of over / under-fitting. Intuitively, these parameters should
        # depend on the train set size. TODO: Tune these parameters.
        dt_regressor = tree.DecisionTreeRegressor(
            max_depth=50,
            min_samples_leaf=2
        )
        RegressionModel.__init__(self, database, dataset, dt_regressor, sparse=False)

    def __str__(self):
        return 'dtr [decision tree regression model]'

# Predicts taxi pickups by averaging past aggregated pickup
# data in the same zone and at the same hour of day.
class BetterBaseline(Model):

    def __init__(self, database, dataset):
        self.db = database
        self.dataset = dataset
        self.table_name = Const.AGGREGATED_PICKUPS

    def train(self):
        '''
        The SQL script to generate the aggregated pickups table is commented out
        because we only need to run it once.

        See Model for comments on the parameters and return value.
        '''
        # Note: this line of code isn't tested yet.
        # os.system('mysql -u root < pickups-aggregated.sql')
        pass

    def predict(self, test_example):
        '''
        Predicts the number of pickups at the specified time and location,
        within a 1 hour interval and 0.01 x 0.01 degrees lat/long box.

        See Model for comments on the parameters and return value.
        '''
        num_pickups = 0.0
        pickup_time = test_example['start_datetime']
        example_id, zone_id = test_example['id'], test_example['zone_id']
        query_string = ('SELECT AVG(num_pickups) as avg_num_pickups FROM %s '
                        'WHERE HOUR(start_datetime) = %d AND zone_id = %d AND '
                        # Hacky way to limit ourself to looking at training
                        # data. This assumes that training data is ordered
                        # by increasing id.
                        'id <= %d') % \
                        (self.table_name, pickup_time.hour, zone_id, 
                        self.dataset.last_train_id)
        results = self.db.execute_query(query_string, fetch_all=False)
        if len(results) == 1:
            num_pickups = float(results[0]['avg_num_pickups'])

        return num_pickups


    def __str__(self):
        return "betterbaseline [baseline version 2]"

# Predicts taxi pickups by averaging past aggregated pickup
# data in the same zone.
class Baseline(Model):

    def __init__(self, database, dataset):
        self.db = database
        self.dataset = dataset
        self.table_name = Const.AGGREGATED_PICKUPS

    def train(self):
        '''
        The SQL script to generate the aggregated pickups table is commented out
        because we only need to run it once.

        See Model for comments on the parameters and return value.
        '''
        # Note: this line of code isn't tested yet.
        # os.system('mysql -u root < pickups-aggregated.sql')
        pass

    def predict(self, test_example):
        '''
        Predicts the number of pickups at the specified time and location, 
        within a 1 hour interval and 0.01 x 0.01 degrees lat/long box.

        See Model for comments on the parameters and return value.
        '''
        num_pickups = 0.0
        pickup_time = test_example['start_datetime']
        example_id, zone_id = test_example['id'], test_example['zone_id']
        query_string = ('SELECT AVG(num_pickups) as avg_num_pickups FROM %s '
                        'WHERE zone_id = %d AND '
                        # Hacky way to limit ourself to looking at training data.
                        'id <= %d') % \
                        (self.table_name, zone_id, self.dataset.last_train_id)
        results = self.db.execute_query(query_string, fetch_all=False)
        if len(results) == 1:
            num_pickups = float(results[0]['avg_num_pickups'])

        return num_pickups

    def __str__(self):
        return "baseline [baseline version 1]"